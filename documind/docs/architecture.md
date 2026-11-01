# DocuMind Architecture

## Status and decisions

This architecture is the Week 9 design baseline. Implementation details may be refined during later milestones, but changes should preserve the product goals of permission-aware retrieval and traceable answers.

| Area | Decision | Rationale |
|---|---|---|
| API backend | Python with FastAPI and Pydantic | Strong support for document-processing and AI libraries, with typed request and response contracts. |
| Relational and vector data | PostgreSQL with pgvector for containerized local use; SQLite with JSON vector storage for native development and tests | Uses 768-dimensional vectors for the selected local embedding model. |
| Original files | Private Azure Blob Storage in deployment; local filesystem behind the same storage interface in development | Separates file bytes from application data while keeping local development inexpensive. |
| Model access | Ollama locally by default (`nomic-embed-text` embeddings and `granite3.3:2b` chat); Azure OpenAI remains an explicit alternative | Makes the portfolio demo work without Azure resources or token-billed inference while keeping provider-specific code behind adapters. Both default models are Apache-2.0 licensed. |
| Processing jobs | PostgreSQL-backed job records and a separate worker process | Supports retryable ingestion without requiring a separate message broker for the MVP. |
| Client | React and TypeScript browser client built with Vite | Provides a typed, interactive document and question workflow while keeping the API deployable independently. |

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

- Workspaces: create and list workspaces for the authenticated user.
- Documents: upload, list, inspect, delete, and request re-indexing.
- Questions: submit a question scoped to a workspace and receive an answer with citations.
- Health: process health and readiness checks that do not expose configuration or secrets.

### Ingestion worker

The worker runs separately from the API but shares the same application code and database. It claims queued document jobs, processes them, and records success or a safe, user-visible failure state. A job is retryable, and repeated processing must not create duplicate chunks for the same document version. Processing claims have a 15-minute lease; stale claims can be re-queued after worker interruption.

### Browser client

The React/TypeScript client connects to the API through a Vite development proxy. In local mode, a user pastes the development bearer token into a connect form; it remains in component memory and clears on disconnect or page refresh. In Entra mode, MSAL uses the configured single-tenant SPA and API scope, caches tokens in memory, and obtains an access token for each private API request. The browser never uses a client secret or persists tokens in local storage. Private mode lists authorized workspaces, creates a workspace, uploads supported documents, refreshes processing status, retries failed processing, deletes documents, submits questions, and displays cited excerpts. The frontend toolchain requires Node.js 20 or newer.

### Authentication modes

`DOCUMIND_AUTH_MODE=local` preserves the development bearer-token workflow. `DOCUMIND_AUTH_MODE=entra` enables API validation of single-tenant Entra access tokens against the configured tenant, client, and API audience. The browser build separately requires `VITE_DOCUMIND_AUTH_MODE` and, for Entra, the tenant ID, SPA client ID, API scope, and redirect URI. Production builds fail when the mode is omitted or Entra settings are incomplete. App registrations, exposed scopes, redirect URIs, and tenant consent are external deployment prerequisites; the application does not create or alter them.

An external identity is keyed by token issuer and subject and maps to a stable internal user ID. Signing in with Entra does not copy local-token identity or workspace memberships.

### Container topology and health

The multi-stage Docker build compiles the browser client and installs the Python API into a non-root runtime image. The same image starts either the API or the ingestion worker. The local Compose profile uses PostgreSQL with pgvector, a private Ollama service, sequential one-shot model downloads, and shared persistent volumes for database, uploads, and model weights. API and worker startup wait until the database and model downloads are ready. Ollama is not published on a host port; inference runs locally on CPU by default. `/health/live` is a process liveness check; `/health/ready` performs a database query and confirms the upload directory is readable and writable. HTTP logs include a generated request ID, method, status, and duration, but not paths, prompts, file contents, tokens, or headers. This single-host local topology is not production HA; deployed environments should use managed PostgreSQL, private blob storage, managed secrets, monitoring/alerts, and durable backups.

### Persistence and model adapters

- PostgreSQL stores users, workspaces, memberships, documents, immutable document versions, processing jobs, chunks, embeddings, and conversation metadata in the deployed application. The current local API uses the same SQLAlchemy model layer with SQLite, storing vectors as JSON only in local mode.
- pgvector stores searchable embeddings alongside chunk records and metadata.
- The database stores storage keys, not public URLs. Local development currently uses the local filesystem storage adapter; private Azure Blob Storage is a separate future milestone and is not included in the auth/demo changes.
- A storage interface separates local development storage from the planned Azure Blob Storage adapter.
- Embedding and chat interfaces isolate the application from Ollama HTTP and Azure OpenAI SDK details and allow deterministic fakes in tests. Nomic document and query inputs use their required `search_document:` and `search_query:` prefixes. Production errors must be surfaced; tests or local development must not silently return success-shaped model output.
- The default embedding space is 768 dimensions. The database records the embedding model identity; startup fails with an explicit re-indexing error if the configured model differs while chunks exist or if legacy vectors cannot be verified. The schema migrates an older PostgreSQL vector column only when it contains no chunks. SQLite applies the same dimension guard.

## Data and access model

- A user can belong to one or more workspaces.
- Entra identities are linked to stable internal users by issuer and subject; this mapping does not copy local-token identity or workspace memberships.
- Documents belong to a workspace and have an owner and processing status.
- Each document version identifies the exact source content used to produce its chunks.
- Chunks belong to a document version and retain source location metadata, such as page number and character offsets where available.
- Embeddings belong to chunks. They are removed or superseded when a document is deleted or re-indexed.
- Every list, retrieval, mutation, and citation lookup is scoped to a workspace the requesting user is authorized to access.

Authorization is enforced server-side. The retrieval query must apply the authorized workspace/document filter before candidate passages are returned to application code or included in model context. A citation identifier must be resolved through the same authorization boundary; clients cannot use guessed IDs to access another workspace's source. Entra identities map to internal users but do not inherit another authentication mode's memberships.

## Document ingestion pipeline

1. The API authenticates the user and verifies permission to add documents to the selected workspace.
2. It validates the declared and detected file type, configured size limit, and upload metadata. Unsupported or malformed files are rejected with an explicit error.
3. The original file is written to private storage. The API records document metadata, an immutable version, and a queued processing job in one database transaction; it does not return a public storage key or URL.
4. The worker claims the job and extracts text for PDF, DOCX, plain-text, or Markdown files. PDF sections retain page numbers.
5. Extracted text is normalized and divided into bounded, overlapping chunks. Each chunk retains its document version and source location.
6. The worker requests prefixed embeddings in batches through the configured embedding provider and persists 768-dimensional chunks and vectors. Tests use an explicit fake provider; production does not fall back to fake embeddings.
7. The worker marks the document version ready only after all required chunks and embeddings are persisted. On failure, it records a safe error state and leaves the job available for an authorized explicit retry.

The original file and derived records are associated with a document version. Re-indexing creates a new version so citations from an existing answer remain tied to the content that was actually indexed.

## Question answering and citation pipeline

1. The API authenticates the user and verifies workspace access.
2. It embeds the question using the configured embedding provider and the model's query-specific input format.
3. PostgreSQL/pgvector performs cosine-distance search with workspace and ready-document filters applied in the query. The SQLite development adapter applies the same filters before ranking candidates in process. Both paths select at most the configured number of chunks that pass the minimum cosine-similarity threshold.
4. If no chunks meet the configured relevance threshold, the API returns a clear “not found in your documents” response without asking the chat model to invent an answer.
5. Otherwise, the chat provider receives the question and bounded source context. Retrieved document text is untrusted input and must never override system instructions.
6. The API returns the answer and citations containing stable document/version references, document title, source location, and the cited excerpt.
7. Citation resolution checks current authorization before returning any source details.

The MVP exposes `POST /api/v1/workspaces/{workspace_id}/questions`. Its response includes the answer, an abstention flag, and only the citations referenced by valid `[n]` markers in the model output. Each citation contains a document/version identifier, filename, page and offset metadata, and the exact retrieved excerpt. If the model returns no citations or references a source number that was not retrieved, the API abstains rather than fabricate citations. The initial similarity threshold is configurable and requires evaluation against a representative question set before production use.

## Security and privacy

- Require authentication for private document, workspace, and question APIs; enforce workspace membership and document scope on the server. The explicitly isolated recruiter-demo routes are the only anonymous exception.
- The local scaffold uses one configured bearer token mapped to one user identity. This supports local workflow testing only; Entra mode provides per-user authentication but does not itself assign workspace memberships.
- Keep uploaded objects private and use short-lived, authorization-checked access if file download is added.
- Validate file size, extension, detected content type, and parser outcomes. Do not trust client-provided MIME types.
- Bound DOCX archive entry counts and total uncompressed size both at upload validation and before extraction to reduce decompression-bomb risk.
- Deletion first records a `deleting` state, removes the stored object, and then removes its metadata. If storage deletion fails, the document remains listed as `delete_failed` so an authorized user can retry; if metadata removal fails after the object is removed, the `deleting` record can also be retried safely.
- Treat source documents and retrieved passages as untrusted content to mitigate prompt injection.
- Never log file contents, extracted text, full prompts, embedding vectors, credentials, or access tokens.
- Keep secrets in environment-specific secret storage; use managed identity for Azure resource access where supported.
- If Azure OpenAI is selected, use an embedding deployment that supports the requested 768 dimensions. Changing embedding models requires re-indexing existing documents; incompatible non-empty databases fail startup rather than mixing vector spaces.
- Delete document chunks, embeddings, and stored originals when a document is deleted, and ensure re-indexing cannot expose stale unauthorized content.

### Public demo

The anonymous demo is pinned to the server-configured `DOCUMIND_DEMO_WORKSPACE_ID`, and that workspace must also be marked `is_public_demo`. Its documents must be synthetic. `GET /api/v1/demo/documents` and `POST /api/v1/demo/questions` accept no workspace identifier and query only that marked workspace; no anonymous upload, workspace mutation, delete, or retry operation is exposed. The seeder refuses to repurpose an existing private workspace.

Both demo routes use an in-process fixed-window limit (30 requests per 60 seconds by default) keyed by the direct client address; forwarded headers are not trusted. This is a single-process development/portfolio safeguard, not a distributed limiter. Before exposure behind a reverse proxy, configure trusted-proxy client address handling. A shared limiter is required before scaling across API processes or instances.

## Observability and failure handling

- Use structured logs with request and job identifiers, event type, workspace/document identifiers where safe, duration, and outcome.
- Track ingestion states such as queued, processing, ready, and failed, plus durations and retry counts.
- Track retrieval/generation latency, number of candidate chunks, provider errors, and whether an answer was grounded without recording user content.
- Return explicit API errors for invalid uploads, denied access, missing documents, and unavailable AI services.
- Provide liveness and readiness endpoints; readiness should reflect required dependencies without returning secrets or internal details.

## Deployment shape

The on-demand portfolio topology is local: FastAPI API, worker, PostgreSQL with pgvector, private Ollama, and local filesystem-backed volumes. Ollama downloads the Apache-2.0 Granite 3.3 2B chat and Nomic Embed Text models once, then serves them privately to the application. Azure OpenAI remains optional for deployments that have suitable regional availability and budget; it is not required for local inference. Production hosting still needs a managed database, private blob storage, managed secrets, monitoring, and an explicit model-cost plan.

## Scope by milestone

- Week 9: select the stack and define component boundaries, data flow, access rules, and failure behavior.
- Week 10: implement document metadata, upload, private storage integration, workspace-scoped listing/inspection, and retryable deletion.
- Week 11: implement PDF/DOCX/text extraction, source-aware chunking, 768-dimensional embeddings, and a retryable worker queue with stale-claim recovery.
- Week 12: implement authorized retrieval, grounded generation, and citation responses.
- Week 13: harden authorization, upload validation, prompt-injection handling, and quality tests.
- Week 14: implement the React browser experience for workspace/document management and cited question answering.
- Week 15: deploy and add operational monitoring.
- Private Azure Blob Storage remains a separate future milestone; the current local filesystem adapter must not be described as production blob storage.
