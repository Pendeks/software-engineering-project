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
- Browser frontend framework to be selected in a later milestone
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

Documents can be listed and inspected only within an authorized workspace. Deletion records progress and keeps failed deletions retryable; upload validation rejects unsupported, mismatched, empty, or oversized files.

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
