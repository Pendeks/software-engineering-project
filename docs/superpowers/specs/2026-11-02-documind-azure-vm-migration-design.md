# DocuMind Azure VM Migration Design

## Intent

Move the existing DocuMind Compose environment off the local machine and onto an Azure Linux VM, retaining Ollama and the existing model behavior. This is intended to free local storage after the Azure copy is verified and the user separately approves local cleanup.

## Goals

- Run the current API, worker, PostgreSQL/pgvector, Ollama, and the same configured chat and embedding models on one Azure Linux VM using Docker Compose.
- Preserve the current database, uploaded files, model configuration, and application behavior by transferring persistent data rather than starting with empty volumes.
- Make the synthetic public demo accessible over HTTPS; keep private workspace access protected by the existing Microsoft Entra sign-in.
- Keep PostgreSQL, Ollama, and internal services inaccessible from the public internet.
- Use the user's Azure for Students subscription and credit only. Do not convert to a paid subscription or knowingly incur charges beyond available credit.
- Keep local Docker data and the recovery backup until the Azure deployment and its data have been verified and the user explicitly approves local cleanup.

## Non-goals

- Replace Ollama with Azure OpenAI or another hosted model provider.
- Move to Azure managed PostgreSQL, Blob Storage, Kubernetes, or a multi-VM architecture.
- Delete local Docker data, the recovery backup, or the user's source documents without separate explicit approval.
- Commit secrets, provision resources, or make public network changes before the design is approved and the user authorizes execution.
- Promise a fixed response latency or a particular monthly cost before VM SKU, quota, remaining credit, and region pricing are checked.

## Approaches

1. **Existing Docker Compose stack on one Azure Linux VM (chosen):** Closest match to the local environment, keeps Ollama and its models, and minimizes application changes. It requires VM and persistent disk management and continuously consumes compute credit while always on.
2. **Managed database/files plus a separate Ollama host:** Less database administration, but splits the environment across services and requires more changes to storage, networking, and backup/restore. It is less faithful to the current setup and does not remove the need to host Ollama.

## Constraints and design

- The current Compose stack uses named volumes for PostgreSQL, uploads, and Ollama models. Migration must back up and restore these to persistent VM storage; it must not recreate them empty.
- The current API port is bound to loopback. Public access therefore needs a deliberate HTTPS reverse-proxy entry point; the proxy must forward only to the API. PostgreSQL and Ollama ports remain private.
- Public Entra sign-in requires the Azure HTTPS origin to be registered as a redirect URI. The user has no custom domain and does not want domain costs. Investigate an Azure-provided DNS name and certificate path; if a valid HTTPS certificate and Entra redirect cannot be achieved without buying a domain, public deployment is blocked rather than downgraded to HTTP.
- The subscription availability check lists VM and network resources in multiple regions, but did not check a specific VM size's quota or remaining student credit. Check both quota and a current cost estimate before provisioning. The estimate must fit within confirmed remaining student credit; do not upgrade the subscription or use a payment method to continue spending.
- The user wants the demo always available. Therefore the design assumes the VM remains running; VM disks continue to incur storage charges when compute is stopped. Azure budget alerts are notifications, not a hard spending cap.
- Start with a CPU VM, not a GPU VM, to limit cost. Confirm model startup and acceptable demo behavior on the selected size before migration is considered complete.
- Local-token identities do not automatically inherit Entra workspace memberships. Use a one-time, operator-run link from the existing local owner to the first verified Entra identity; this adds no Azure service or recurring cost and preserves existing workspace access.
- Keep SSH restricted to the user's administrative source address or an equivalent secure management path. Only HTTPS should be generally internet-accessible; HTTP may be used only for certificate issuance/redirect if required.
- Transfer data with an explicit backup/restore procedure and verify document counts, uploads, model availability, indexing, question answering, public-demo isolation, and Entra-protected private access before any local cleanup.
- Keep Azure secrets in an untracked VM environment file or secure secret mechanism; do not put credentials in the repository or deployment logs.
- After successful verification and a separate explicit cleanup confirmation, remove the local DocuMind Docker environment and its database, upload, and model volumes. Preserve the recovery backup and do not prune unrelated Docker projects or data.

## Acceptance criteria

- A named Azure Linux VM runs the same Compose application services and configured Ollama models with persistent disks.
- PostgreSQL and Ollama are not reachable from the public internet; only the planned web ingress is exposed.
- The public demo is served over HTTPS and private workspace sign-in completes through the configured Entra redirect URI.
- Restored database records, uploaded document bytes, and model configuration are verified against the local source before cutover.
- The intended Entra user can access the existing local owner's private workspaces through the one-time verified identity link; unrelated Entra identities cannot.
- VM size, region, quota, and cost are checked before provisioning; the chosen configuration does not knowingly exceed confirmed Azure for Students credit.
- The user can reach the demo while the VM is on, and understands that deallocating the VM makes it unavailable while managed disks continue to incur storage charges.
- Local Docker images, volumes, and VHDX files remain intact until the Azure copy passes verification and the user explicitly approves cleanup; cleanup preserves the recovery backup and unrelated Docker data.
