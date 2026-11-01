# DocuMind Azure-First Compose Design

## Intent

Allow DocuMind to run with Azure OpenAI without starting Ollama or downloading local model weights. This reduces local Docker disk use while retaining the existing database and uploaded-file volumes.

## Goals

- Make the normal Compose startup use the configured Azure OpenAI provider and omit Ollama services.
- Keep local Ollama inference available as an explicit opt-in.
- Preserve the database and upload volumes in both modes.
- Document the Azure and local startup requirements, including that existing documents may need re-embedding when changing embedding models.

## Non-goals

- Provision Azure resources, configure a deployment, or add credentials.
- Move the API, database, or uploaded files to Azure.
- Delete, prune, migrate, or compact any local Docker data or volumes.
- Change non-Compose Python defaults or the application’s Azure OpenAI client.

## Approaches

1. **Azure-first Compose with optional Ollama profile (chosen):** Normal startup omits Ollama; users explicitly enable its profile for local inference. This best serves the storage goal and keeps local inference available, but changes the current local-first Compose startup.
2. **Preserve local-first startup and add an Azure-specific Compose entry point:** Less disruption to current setup, but introduces a second maintained configuration and requires users to select it explicitly.

## Constraints and design

- The project already supports Azure OpenAI and requests 768-dimensional embeddings, matching its current vector schema.
- Azure OpenAI standard deployments are pay-per-token; exact charges depend on chat and embedding usage.
- Both tested model deployments were available in West US, East US, and East US 2 for the user's subscription. Deployment quota was not checked.
- Azure mode must not start or pull Ollama. Local mode must still wait for Ollama and its model-download jobs before serving inference.
- Existing persistent volumes must remain untouched. Users who switch embedding models should reprocess existing documents so retrieval uses vectors from the new embedding model.
- No Azure keys or other secrets are to be written into tracked files.

## Acceptance criteria

- Default `docker compose up` does not start Ollama or either model-pull service.
- Azure mode starts the API, worker, and database without local model configuration or Ollama dependencies.
- An explicit local-mode command starts Ollama, downloads the configured models, and preserves readiness ordering.
- Compose configuration validates in both modes.
- README setup instructions describe both modes and their required environment variables.
- Database and upload volume declarations and names remain unchanged.
