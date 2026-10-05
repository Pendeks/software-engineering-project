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
- Private Azure Blob Storage for original files
- Azure OpenAI behind embedding and chat provider interfaces
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

The local default stores metadata in `var/documind.db` and private file bytes in `var/uploads/`. Settings can also be read from a local `.env` file based on `.env.example`. The token is required for document and workspace APIs; the current local setup maps that one token to one configured user identity. It is a development scaffold, not production authentication. Do not expose it publicly or reuse a real credential. Production requires per-user authentication and authorization.

Documents can be listed and inspected only within an authorized workspace. Deletion records progress and keeps failed deletions retryable; upload validation rejects unsupported, mismatched, empty, or oversized files. DOCX archives are also checked for excessive expanded size and entry count before parsing, to reduce decompression-bomb risk.

Uploads are queued for processing automatically. Configure `DOCUMIND_AZURE_OPENAI_ENDPOINT`, `DOCUMIND_AZURE_OPENAI_API_KEY`, and `DOCUMIND_AZURE_OPENAI_EMBEDDING_DEPLOYMENT` (a deployment returning 1536 dimensions) in `.env`; do not commit that file. Start the worker in a second terminal:

```powershell
python -m documind.worker
```

The worker extracts PDF, DOCX, TXT, and Markdown content, creates overlapping chunks with source offsets (and PDF page numbers), and persists 1536-dimensional vectors in PostgreSQL/pgvector. SQLite uses JSON only as a local test adapter. The worker leaves a safe failure status when model configuration or processing is unavailable. Failed jobs can be retried explicitly; jobs stuck in `processing` become retryable after the 15-minute lease expires.

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

Open `http://127.0.0.1:5173`. The development server proxies API requests to `http://127.0.0.1:8000`. Paste the bearer token configured for the API to connect; the browser holds it in memory only and clears it when disconnected or refreshed. Create or select a workspace, upload documents, follow indexing status, and ask questions against ready documents with source excerpts.

## Containerized local deployment

Docker Desktop with Docker Compose v2 is required. From this directory, create a local environment file and set fresh, random values for the API token and local PostgreSQL password in the current PowerShell session:

```powershell
Copy-Item .env.example .env
$env:DOCUMIND_API_TOKEN = [guid]::NewGuid().ToString("N")
$env:DOCUMIND_POSTGRES_PASSWORD = [guid]::NewGuid().ToString("N")
docker compose up --build
```

Open `http://127.0.0.1:8000`. The compose stack runs PostgreSQL with pgvector, the API (including the built browser app), and the ingestion worker. Uploaded files and database data are held in local named volumes. Use `docker compose logs -f api worker` to inspect service logs; do not publish these development services directly to the internet. Stop them with `docker compose down`; persistent volumes remain until explicitly removed.

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
