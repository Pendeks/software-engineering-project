# DocuMind Azure-First Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Azure OpenAI the normal Compose mode so Docker does not start Ollama or download local model weights, while retaining local inference as an explicit option.

**Architecture:** Keep the existing API, worker, database, and persistent upload/database volumes. Put Ollama and its one-shot model download services behind an `ollama` profile, make their API/worker dependencies optional when that profile is off, and preserve readiness ordering when it is on. Set the Compose-facing provider default to Azure OpenAI; keep Azure credentials external to tracked files.

**Tech Stack:** Docker Compose, environment configuration, Markdown documentation.

**Spec:** `docs/superpowers/specs/2026-11-02-documind-azure-first-compose-design.md`

## Global Constraints

- Azure mode must not start or pull Ollama. Local mode must still wait for Ollama and its model-download jobs before serving inference.
- Existing persistent volumes must remain untouched. Users who switch embedding models should reprocess existing documents so retrieval uses vectors from the new embedding model.
- No Azure keys or other secrets are to be written into tracked files.
- Do not provision Azure resources, configure a deployment, or delete, prune, migrate, or compact local Docker data or volumes.
- Do not change non-Compose Python defaults or the application’s Azure OpenAI client.

## Review Focus

- Default Compose configuration accidentally activates any Ollama or model-pull service — Task 1 checks that the default service list omits all three services.
- Local mode loses Ollama health/model-download ordering — Task 1 checks the profiled configuration retains the existing API/worker dependencies and conditions.
- A custom model provider setting is ignored — Task 1 checks provider overrides for both Azure and Ollama modes.
- A persistent database or upload volume is renamed or dropped — Task 1 checks the configured volume names and mounts in both modes.
- Example credentials are committed or required merely to render Compose — Task 1 checks `.env.example` keeps credentials blank and both configurations can be rendered with validation-only placeholder values.

---

### Task 1: Configure Azure-first Compose and document local opt-in

**Files:**
- Modify: `documind/compose.yaml`
- Modify: `documind/.env.example`
- Modify: `documind/README.md`

**Interfaces:**
- Consumes: Existing `DOCUMIND_MODEL_PROVIDER`, Azure OpenAI endpoint/key/deployment settings, and Ollama model settings.
- Produces: Default Compose provider `azure_openai`; profile name `ollama`; local-mode command `docker compose --profile ollama up --build`.

- [ ] **Step 1: Set the Compose provider and service defaults**

Use `azure_openai` as the Compose fallback provider. Put `ollama`, `ollama-embedding-model`, and `ollama-chat-model` in the `ollama` profile. Make API and worker dependencies on those profiled services optional while retaining the existing health and model-download conditions when the profile is enabled. Keep the database dependency required and do not change named-volume names.

- [ ] **Step 2: Update the example environment**

Set the documented Compose provider to Azure OpenAI by default. Keep Azure endpoint, API key, chat deployment, and embedding deployment empty; retain the existing Ollama model names for users who opt into the profile. Do not add real credentials.

- [ ] **Step 3: Document Azure and local startup**

Update the README to explain that normal Compose startup omits Ollama, that Azure endpoint/key/deployment settings are needed for model requests, and that local Ollama requires `DOCUMIND_MODEL_PROVIDER=ollama` plus `docker compose --profile ollama up --build`. Explain that changing the embedding model requires reprocessing existing documents, and that stopping/removing containers does not itself delete persistent volumes.

- [ ] **Step 4: Validate both Compose modes**

Run in PowerShell from `documind` with validation-only values for the required API token and database password:

```powershell
$env:DOCUMIND_API_TOKEN = "compose-validation-only"
$env:DOCUMIND_POSTGRES_PASSWORD = "compose-validation-only"
$env:DOCUMIND_MODEL_PROVIDER = "azure_openai"
$env:COMPOSE_PROFILES = ""
docker compose config -q
$defaultServices = docker compose config --services
if ($defaultServices -contains "ollama" -or $defaultServices -contains "ollama-embedding-model" -or $defaultServices -contains "ollama-chat-model") { throw "Default Compose unexpectedly includes Ollama services." }
$env:DOCUMIND_MODEL_PROVIDER = "ollama"
docker compose --profile ollama config -q
$localServices = docker compose --profile ollama config --services
if (-not ($localServices -contains "ollama" -and $localServices -contains "ollama-embedding-model" -and $localServices -contains "ollama-chat-model")) { throw "Ollama profile is missing a required service." }
```

Expected: both Compose configurations validate; the default service list excludes Ollama and model-pull services; the explicit local profile includes all three. Inspect the normalized local configuration to confirm API and worker still wait for Ollama health and successful model downloads, and confirm the database/upload volume names are unchanged. Run `git diff --check`.
