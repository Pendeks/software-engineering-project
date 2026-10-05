# DocuMind Architecture

## Status and decisions

This architecture is the Week 9 design baseline. Implementation details may be refined during later milestones, but changes should preserve the product goals of permission-aware retrieval and traceable answers.

| Area | Decision | Rationale |
|---|---|---|
| API backend | Python with FastAPI and Pydantic | Strong support for document-processing and AI libraries, with typed request and response contracts. |
| Relational and vector data | PostgreSQL with pgvector for deployment; SQLite with JSON vector storage for local development and tests | Keeps local workflow tests independent of PostgreSQL while using pgvector's 1536-dimensional vector type in deployment. |
| Original files | Private Azure Blob Storage in deployment; local filesystem behind the same storage interface in development | Separates file bytes from application data while keeping local development inexpensive. |
| Model access | Azure OpenAI behind separate embedding and chat provider interfaces | Allows the MVP to use managed models while keeping model-specific code out of API and retrieval logic. Model deployments and quotas must be confirmed before deployment. |
| Processing jobs | PostgreSQL-backed job records and a separate worker process | Supports retryable ingestion without requiring a separate message broker for the MVP. |
| Client | Browser client calling the API; framework selection deferred | Week 9 focuses on the backend and data pipelines. |

## Architecture goals

- Provide a document-focused knowledge workspace, not a general-purpose chatbot.
- Return answers grounded in retrieved passages, with citations to their source documents.
- Enforce workspace and document authorization before source text is sent to a model.
- Make ingestion and answer generation observable without logging document contents or prompts.
- Keep the MVP deployable with a small number of services and a student-budget-aware footprint.

## Components and boundaries

### API service

The FastAPI service owns the HTTP API, request validation, authentication and authorization checks, document metadata, job creation, retrieval orchestration, and response shaping. It does not parse files or call model SDKs directly inside route handlers; those operations go through application services and provider interfaces.

Initial API areas:

- Documents: upload, list, inspect, delete, and request re-indexing.
- Questions: submit a question scoped to a workspace and receive an answer with citations.
- Health: process health and readiness checks that do not expose configuration or secrets.

### Ingestion worker

The worker runs separately from the API but shares the same application code and database. It claims queued document jobs, processes them, and records success or a safe, user-visible failure state. A job is retryable, and repeated processing must not create duplicate chunks for the same document version. Processing claims have a 15-minute lease; stale claims can be re-queued after worker interruption.

### Persistence and model adapters

- PostgreSQL stores users, workspaces, memberships, documents, immutable document versions, processing jobs, chunks, embeddings, and conversation metadata in the deployed application. The current local API uses the same SQLAlchemy model layer with SQLite, storing vectors as JSON only in local mode.
- pgvector stores searchable embeddings alongside chunk records and metadata.
- A private blob container stores original files. The database stores blob keys, not public URLs.
- A storage interface separates local development storage from Azure Blob Storage.
- Embedding and chat interfaces isolate the application from Azure OpenAI SDK details and allow deterministic fakes in tests. Production errors must be surfaced; tests or local development must not silently return success-shaped model output.

## Data and access model

- A user can belong to one or more workspaces.
- Documents belong to a workspace and have an owner and processing status.
- Each document version identifies the exact source content used to produce its chunks.
- Chunks belong to a document version and retain source location metadata, such as page number and character offsets where available.
- Embeddings belong to chunks. They are removed or superseded when a document is deleted or re-indexed.
- Every list, retrieval, mutation, and citation lookup is scoped to a workspace the requesting user is authorized to access.

Authorization is enforced server-side. The retrieval query must apply the authorized workspace/document filter before candidate passages are returned to application code or included in model context. A citation identifier must be resolved through the same authorization boundary; clients cannot use guessed IDs to access another workspace's source.

## Document ingestion pipeline

1. The API authenticates the user and verifies permission to add documents to the selected workspace.
2. It validates the declared and detected file type, configured size limit, and upload metadata. Unsupported or malformed files are rejected with an explicit error.
3. The original file is written to private storage. The API records document metadata, an immutable version, and a queued processing job in one database transaction; it does not return a public storage key or URL.
4. The worker claims the job and extracts text for PDF, DOCX, plain-text, or Markdown files. PDF sections retain page numbers.
5. Extracted text is normalized and divided into bounded, overlapping chunks. Each chunk retains its document version and source location.
6. The worker requests embeddings in batches through the Azure OpenAI embedding provider and persists 1536-dimensional chunks and vectors. Tests use an explicit fake provider; production does not fall back to fake embeddings.
7. The worker marks the document version ready only after all required chunks and embeddings are persisted. On failure, it records a safe error state and leaves the job available for an authorized explicit retry.

The original file and derived records are associated with a document version. Re-indexing creates a new version so citations from an existing answer remain tied to the content that was actually indexed.

## Question answering and citation pipeline

1. The API authenticates the user and verifies workspace access.
2. It embeds the question using the configured embedding provider.
3. PostgreSQL/pgvector performs cosine-distance search with workspace and ready-document filters applied in the query. The SQLite development adapter applies the same filters before ranking candidates in process. Both paths select at most the configured number of chunks that pass the minimum cosine-similarity threshold.
4. If no chunks meet the configured relevance threshold, the API returns a clear “not found in your documents” response without asking the chat model to invent an answer.
5. Otherwise, the chat provider receives the question and bounded source context. Retrieved document text is untrusted input and must never override system instructions.
6. The API returns the answer and citations containing stable document/version references, document title, source location, and the cited excerpt.
7. Citation resolution checks current authorization before returning any source details.

The MVP exposes `POST /api/v1/workspaces/{workspace_id}/questions`. Its response includes the answer, an abstention flag, and only the citations referenced by valid `[n]` markers in the model output. Each citation contains a document/version identifier, filename, page and offset metadata, and the exact retrieved excerpt. If the model returns no citations or references a source number that was not retrieved, the API abstains rather than fabricate citations. The initial similarity threshold is configurable and requires evaluation against a representative question set before production use.

## Security and privacy

- Require authentication for document and question APIs; enforce workspace membership and document scope on the server.
- The current local scaffold uses one configured bearer token mapped to one user identity. This supports local workflow testing only; it is not a substitute for per-user production authentication or workspace invitations.
- Keep uploaded objects private and use short-lived, authorization-checked access if file download is added.
- Validate file size, extension, detected content type, and parser outcomes. Do not trust client-provided MIME types.
- Deletion first records a `deleting` state, removes the stored object, and then removes its metadata. If storage deletion fails, the document remains listed as `delete_failed` so an authorized user can retry; if metadata removal fails after the object is removed, the `deleting` record can also be retried safely.
- Treat source documents and retrieved passages as untrusted content to mitigate prompt injection.
- Never log file contents, extracted text, full prompts, embedding vectors, credentials, or access tokens.
- Keep secrets in environment-specific secret storage; use managed identity for Azure resource access where supported.
- Configure the Azure OpenAI embedding deployment to return 1536 dimensions to match the pgvector column.
- Delete document chunks, embeddings, and stored originals when a document is deleted, and ensure re-indexing cannot expose stale unauthorized content.

## Observability and failure handling

- Use structured logs with request and job identifiers, event type, workspace/document identifiers where safe, duration, and outcome.
- Track ingestion states such as queued, processing, ready, and failed, plus durations and retry counts.
- Track retrieval/generation latency, number of candidate chunks, provider errors, and whether an answer was grounded without recording user content.
- Return explicit API errors for invalid uploads, denied access, missing documents, and unavailable AI services.
- Provide liveness and readiness endpoints; readiness should reflect required dependencies without returning secrets or internal details.

## Deployment shape

The initial cloud topology consists of the FastAPI API, a worker process using the same application image, PostgreSQL with pgvector, private Azure Blob Storage, and Azure OpenAI deployments. The API and worker may be deployed as separate container workloads. Confirm Azure model availability, student subscription quota, and expected cost before provisioning. Local document-management development uses SQLite and filesystem storage without Azure credentials; retrieval and embeddings remain out of scope until later milestones.

## Scope by milestone

- Week 9: select the stack and define component boundaries, data flow, access rules, and failure behavior.
- Week 10: implement document metadata, upload, private storage integration, workspace-scoped listing/inspection, and retryable deletion.
- Week 11: implement PDF/DOCX/text extraction, source-aware chunking, 1536-dimensional embeddings, and a retryable worker queue with stale-claim recovery.
- Week 12: implement authorized retrieval, grounded generation, and citation responses.
- Week 13: harden authorization, upload validation, prompt-injection handling, and quality tests.
- Week 14: implement the browser experience.
- Week 15: deploy and add operational monitoring.
