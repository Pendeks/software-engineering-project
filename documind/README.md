# DocuMind

## Overview

DocuMind is an AI-powered document intelligence platform that allows users to upload documents and ask questions about their content using retrieval-augmented generation (RAG).

## What makes DocuMind different

DocuMind is not intended to be a general-purpose chatbot. It is a purpose-built, permission-aware knowledge workspace for asking questions across a team's managed documents.

- Answers should link to the exact source passages used, and clearly say when the documents do not support an answer.
- Teams can upload, organize, update, and delete documents; DocuMind handles extraction, indexing, and retrieval.
- Workspace access controls ensure users can only retrieve documents they are authorized to see.
- Ingestion and retrieval activity is observable so teams can investigate processing failures and answer quality.

General-purpose AI assistants may also analyze uploaded files. DocuMind's intended value is the managed document lifecycle, permission-aware retrieval, and traceable answers across a team's own materials.

**Product pitch:** Ask questions across your team's documents and get answers linked to the exact sources you're allowed to access.

## Core goals

- Support document upload and storage
- Extract and clean text from documents
- Chunk content for retrieval
- Generate embeddings and search semantically
- Generate grounded answers using an LLM
- Show source attribution and citations
- Demonstrate secure document access controls

## Selected technology direction

- Python and FastAPI backend
- PostgreSQL with pgvector for deployment metadata, chunks, and vector search; SQLite is used for local document-management development
- Planned private Azure Blob Storage for production; the current implementation uses local filesystem storage
- Local Ollama embedding and chat models by default, with Azure OpenAI as an optional provider
- Separate API and ingestion worker processes
- React and Vite browser frontend
- Docker
- Azure hosting
- GitHub Actions

See [the architecture](./docs/architecture.md) for component boundaries, ingestion and question-answering flows, security constraints, and milestone scope. Azure model deployments and quotas must be confirmed before deployment.

## Local document API

Requires Python 3.11 or newer. From this directory, create an environment and install the app with its test dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
$env:DOCUMIND_API_TOKEN = [guid]::NewGuid().ToString("N")
uvicorn documind.main:app --reload --app-dir src
```

The local default stores metadata in `var/documind.db` and private file bytes in `var/uploads/`. Settings can also be read from a local `.env` file based on `.env.example`; `DOCUMIND_AUTH_MODE=local` preserves the development bearer-token workflow. The token is required for document and workspace APIs and maps to one configured user identity. It is a development scaffold, not production authentication. Do not expose it publicly or reuse a real credential. For per-user Entra sign-in, see [Entra sign-in and the public demo](#entra-sign-in-and-the-public-demo).

Documents can be listed and inspected only within an authorized workspace. Deletion records progress and keeps failed deletions retryable; upload validation rejects unsupported, mismatched, empty, or oversized files. The API also caps upload request bodies before multipart parsing, including requests without a declared content length. DOCX archives are checked for excessive expanded size and entry count before parsing, to reduce decompression-bomb risk.

Uploads are queued for processing automatically. The default local provider uses Ollama with `nomic-embed-text` for embeddings and `granite3.3:2b` for chat. Install and start [Ollama](https://ollama.com/download), then pull the models:

```powershell
ollama pull nomic-embed-text
ollama pull granite3.3:2b
```

Both models are Apache-2.0 licensed ([embedding model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5), [chat model card](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct)). Ollama performs inference locally; no Azure model deployment or token-billed API is needed. The first download requires an internet connection and uses local disk space.

To opt into Azure instead, set `DOCUMIND_MODEL_PROVIDER=azure_openai` and configure `DOCUMIND_AZURE_OPENAI_ENDPOINT`, `DOCUMIND_AZURE_OPENAI_API_KEY`, `DOCUMIND_AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, and `DOCUMIND_AZURE_OPENAI_CHAT_DEPLOYMENT` in `.env`; do not commit that file. The embedding deployment must support the requested 768-dimensional output.

Start the worker in a second terminal:

```powershell
python -m documind.worker
```

The worker extracts PDF, DOCX, TXT, and Markdown content, creates overlapping chunks with source offsets (and PDF page numbers), and persists 768-dimensional vectors in PostgreSQL/pgvector. Nomic embeddings use `search_document:` for indexed passages and `search_query:` for questions. SQLite uses JSON for local development and tests. The worker leaves a safe failure status when model configuration or processing is unavailable. Failed jobs can be retried explicitly; jobs stuck in `processing` become retryable after the 15-minute lease expires. The database records the embedding model identity and dimension; startup refuses incompatible or untracked existing vectors rather than mixing models. Back up and re-index existing documents before changing embedding models.

Create a workspace and upload a text document using the token configured in your current PowerShell session:

```powershell
$headers = @{ Authorization = "Bearer $env:DOCUMIND_API_TOKEN" }
$workspace = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/workspaces -Headers $headers -ContentType "application/json" -Body '{"name":"Team Docs"}'
curl.exe -X POST "http://127.0.0.1:8000/api/v1/workspaces/$($workspace.id)/documents" -H "Authorization: Bearer $env:DOCUMIND_API_TOKEN" -F "file=@example.txt"
```

```powershell
$documents = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/workspaces/$($workspace.id)/documents" -Headers $headers
$documentId = $documents[0].id
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/workspaces/$($workspace.id)/documents/$documentId/process" -Headers $headers
```

For question answering, also set `DOCUMIND_AZURE_OPENAI_CHAT_DEPLOYMENT` to a chat-model deployment. The API embeds the question, searches only ready chunks in the authorized workspace, and returns source excerpts for citations. The default retrieval limit is five chunks and the minimum cosine similarity is `0.2`; tune `DOCUMIND_RETRIEVAL_TOP_K` and `DOCUMIND_RETRIEVAL_MIN_SIMILARITY` against an evaluation set before relying on production answers. If no source passes the threshold, or the model omits valid citations, the API abstains.

```powershell
$question = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/workspaces/$($workspace.id)/questions" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ question = "What does the document say?" } | ConvertTo-Json)
$question
```

Run the focused API and processing tests with `python -m pytest`.

## Browser experience

Requires Node.js 20 or newer. In another terminal, install the frontend dependencies once and start the Vite development server:

```powershell
Set-Location web
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The development server proxies API requests to `http://127.0.0.1:8000`. In local auth mode, paste the API bearer token to connect; the browser holds it in memory only and clears it when disconnected or refreshed. Create or select a workspace, upload documents, follow indexing status, and ask questions against ready documents with source excerpts. The landing page also offers a separate no-login public demo when the demo workspace is provisioned.

## Entra sign-in and the public demo

Entra mode requires deployment-owner setup before it can be used. Register the API application, expose the API scope, register the single-page application (SPA), configure its redirect URI, and grant the required consent in your tenant. The code does not create registrations, grant consent, provision cloud resources, or manage tenant credentials.

Set the API's `.env` values to `DOCUMIND_AUTH_MODE=entra`, `DOCUMIND_ENTRA_TENANT_ID`, `DOCUMIND_ENTRA_CLIENT_ID`, and `DOCUMIND_ENTRA_API_AUDIENCE`. Configure the frontend build with `VITE_DOCUMIND_AUTH_MODE=entra`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_CLIENT_ID`, `VITE_ENTRA_API_SCOPE`, and `VITE_ENTRA_REDIRECT_URI`. The tenant and client IDs must match the registrations; the API audience and browser scope must match the API's exposed scope. For direct Vite development, set these `VITE_` variables in the shell that starts Vite. Docker Compose passes them from the project `.env` file as build arguments. Production builds reject missing Entra settings and all builds reject an unspecified auth mode. The browser uses MSAL's in-memory cache; never put a client secret in frontend configuration or the browser bundle.

Entra identities are mapped to stable internal users by token issuer and subject. Local-token users' workspace memberships are not automatically transferred when switching auth modes.

The public demo is deliberately separate from private sign-in. It exposes only the configured, explicitly marked demo workspace and must contain synthetic content only. Provision it with `DOCUMIND_DEMO_WORKSPACE_ID` set to a stable ID (for example, `recruiter-demo`) and run:

```powershell
python -m documind.seed_demo
python -m documind.worker
```

Run the seed command once against the same database and storage used by the API; the existing worker indexes its queued documents. In Compose, set `DOCUMIND_DEMO_WORKSPACE_ID` in `.env`, start the services, then run `docker compose exec api python -m documind.seed_demo`. The demo offers document listing and question answering only: it has no upload, workspace, delete, or retry operations, and it does not accept a workspace ID from the browser.

The demo has an in-process fixed-window limit of 30 requests per 60 seconds per client address by default. It ignores untrusted `X-Forwarded-For` values. This limit is per API process; before public exposure behind a reverse proxy, configure trusted-proxy client-address handling, and use a shared limiter before running multiple API processes or instances.

## Containerized local deployment

Docker Desktop with Docker Compose v2 is required. From this directory, create a local environment file and set fresh, random values for the API token and local PostgreSQL password in the current PowerShell session:

```powershell
Copy-Item .env.example .env
$env:DOCUMIND_API_TOKEN = [guid]::NewGuid().ToString("N")
$env:DOCUMIND_POSTGRES_PASSWORD = [guid]::NewGuid().ToString("N")
docker compose up --build
```

Open `http://127.0.0.1:8000`. Compose builds the browser in local auth mode by default; set the Entra build-time `VITE_` settings above to select Entra mode. The stack runs PostgreSQL with pgvector, a private Ollama service, one-shot model download services, the API (including the built browser app), and the ingestion worker. Initial startup downloads the model weights; subsequent runs reuse the persistent model volume. Inference is CPU-based by default. The Ollama API is not published to the host. Uploaded files, database data, and model weights are held in local named volumes. Use `docker compose logs -f api worker` to inspect service logs; do not publish these development services directly to the internet. Stop them with `docker compose down`; persistent volumes remain until explicitly removed.

To connect the browser, retrieve the local token from `.env` in PowerShell and paste it into the connect form:

```powershell
(Get-Content .env | Where-Object { $_ -match '^DOCUMIND_API_TOKEN=' } | Select-Object -Last 1) -replace '^DOCUMIND_API_TOKEN=', ''
```

The container image runs as a non-root user and exposes `/health/live` and `/health/ready`. Readiness checks the database connection and local upload storage. This compose setup is a local demonstration topology, not a highly available production deployment: production should use managed PostgreSQL, private blob storage, secret management, and an explicit backup/retention plan.

## Planned milestones

- Foundation
- RAG MVP
- Deployed

## Project docs

Planned documentation includes:

- AI architecture
- Document-processing pipeline
- RAG design
- Security and prompt-injection review
- Observability and processing metrics
- Deployment notes

## Notes

The project should prioritize secure handling of uploaded content, robust retrieval quality, and transparent source-grounded responses.
