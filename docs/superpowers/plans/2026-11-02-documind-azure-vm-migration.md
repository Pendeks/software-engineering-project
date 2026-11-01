# DocuMind Azure VM Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the current DocuMind Docker Compose application and its persistent data to an always-on Azure Linux VM while keeping the same Ollama models and providing a secure HTTPS public demo.

**Architecture:** Preflight Azure credit, VM quota, and region pricing before provisioning anything. Provision one Linux VM with Bicep, run the existing Compose services with a Caddy HTTPS reverse-proxy overlay, and transfer consistent PostgreSQL, uploads, and Ollama model backups. Verify the migrated environment and Entra access before a separately confirmed, narrowly scoped local cleanup.

**Tech Stack:** Azure Bicep, Azure Linux VM, Docker Compose, Ollama, PostgreSQL/pgvector, Caddy, Microsoft Entra ID, PowerShell/SSH.

**Spec:** `docs/superpowers/specs/2026-11-02-documind-azure-vm-migration-design.md`

## Global Constraints

- Keep the API, worker, PostgreSQL/pgvector, Ollama, and the same configured models on one Azure Linux VM.
- Use the user's Azure for Students subscription and credit only; do not convert to a paid subscription or knowingly incur charges beyond available credit.
- The user wants the demo always available. Therefore the design assumes the VM remains running; VM disks continue to incur storage charges when compute is stopped.
- Start with a CPU VM, not a GPU VM, to limit cost. Confirm model startup and acceptable demo behavior on the selected size before migration is considered complete.
- The current Compose stack uses named volumes for PostgreSQL, uploads, and Ollama models. Migration must back up and restore these to persistent VM storage; it must not recreate them empty.
- PostgreSQL and Ollama ports remain private. Only HTTPS should be generally internet-accessible; SSH must be restricted to the user's administrative source address or an equivalent secure management path.
- If valid HTTPS and Entra redirect cannot be achieved without buying a domain, public deployment is blocked rather than downgraded to HTTP.
- Verify document counts, uploads, model availability, indexing, question answering, public-demo isolation, and Entra-protected private access before any local cleanup.
- Keep Azure secrets in an untracked VM environment file or secure secret mechanism; do not put credentials in the repository or deployment logs.
- After successful verification and a separate explicit cleanup confirmation, remove only the local DocuMind Docker environment and its volumes. Preserve the recovery backup and unrelated Docker projects/data.
- Do not provision resources, transfer data, or clean local Docker data as part of plan authoring; execution requires separate user authorization.

## Review Focus

- Azure credit or VM quota is insufficient for the requested always-on service — Task 1 gates all provisioning on confirmed balance, SKU quota, and an estimated monthly cost.
- Data is inconsistent or incomplete after transfer — Task 4 stops writes for the snapshot, compares database counts and upload hashes, and restores the exact Ollama model volume.
- Public access exposes Ollama, PostgreSQL, SSH, or local-token-only private APIs — Tasks 2 and 3 validate the NSG, Compose bindings, HTTPS proxy, and Entra mode.
- Entra users cannot access existing private workspaces because local-token identities do not automatically map — Task 3 safely links the first verified Entra identity to the existing local owner; Task 5 tests workspace access.
- Proxy traffic collapses into one demo rate-limit bucket or trusts spoofed forwarded headers — Task 2 trusts forwarded client addresses only from Caddy; Task 5 validates per-client rate limiting through the public endpoint.

---

### Task 1: Verify Azure credit, quota, and a viable always-on VM size

**Files:**
- No repository files changed.

**Interfaces:**
- Consumes: The supplied Azure for Students subscription and the VM/network regions currently allowed for it.
- Produces: A confirmed deployment region, CPU VM SKU, OS disk size, monthly estimate, and a go/no-go decision. Do not retain the subscription ID or credit details in repository files.

- [ ] **Step 1: Check remaining Azure for Students credit and expiry**

Use the Azure portal billing/subscription view; record the remaining credit and expiration for this execution only. Do not change subscription offer or attach a paid payment method.

- [ ] **Step 2: Check VM SKU availability and quota in candidate regions**

Use Azure VM SKU/quota checks for the allowed regions, including Indonesia Central and nearby allowed regions. Select a CPU size with at least 8 GiB RAM as the initial Ollama candidate, then verify availability and vCPU quota for the exact SKU. If no qualifying SKU is available, stop and present alternatives without provisioning.

- [ ] **Step 3: Estimate the always-on monthly cost**

Price the selected VM, a 64-GiB Standard SSD OS disk, static Standard public IPv4, and expected outbound traffic in the selected region. Compare a 30-day estimate against confirmed remaining student credit and its expiry. Account for the public IP and managed disk continuing to cost money when the VM is deallocated.

- [ ] **Step 4: Obtain a provisioning go-ahead**

Present the selected region/SKU, monthly estimate, available credit/expiry, public ingress costs, and any uncertainty to the user. Proceed only after they explicitly authorize Azure resource creation. If the estimate does not fit the confirmed credit or the user declines, stop without creating resources.

---

### Task 2: Add secure, reproducible Azure VM and HTTPS deployment configuration

**Files:**
- Create: `documind/infra/main.bicep`
- Create: `documind/infra/cloud-init.yaml`
- Create: `documind/infra/Caddyfile`
- Create: `documind/compose.azure.yaml`
- Test: Compose configuration validation and Bicep compilation

**Interfaces:**
- Consumes: Task 1's approved region, VM SKU, SSH source CIDR, and DNS label.
- Produces: Bicep parameters for location, size, admin username/public SSH key, allowed SSH CIDR, DNS label, and disk size; Compose overlay exposing only Caddy on ports 80/443 and proxying to the private API.

- [ ] **Step 1: Define the VM/network deployment parameters and resources**

Create `main.bicep` for one Ubuntu Linux VM, static Standard public IPv4 with Azure DNS label, VNet/subnet, NIC, and NSG. Allow inbound TCP 80/443; allow TCP 22 only from the supplied SSH source CIDR. Use SSH public-key authentication, a 64-GiB Standard SSD OS disk, and the SKU approved in Task 1. Do not create model-service, database, or API public ports or store credentials.

- [ ] **Step 2: Install Docker prerequisites through cloud-init**

Create `cloud-init.yaml` to install Docker Engine and the Compose plugin, enable Docker at boot, and avoid copying application secrets or data into cloud-init/user-data.

- [ ] **Step 3: Add the Azure-only Caddy Compose overlay**

Create `compose.azure.yaml` with Caddy listening on host ports 80 and 443, persistent Caddy certificate/config volumes, and a route to `api:8000`. Configure the frontend origin as the Azure DNS-label HTTPS hostname. Keep PostgreSQL and Ollama unpublished; leave the existing local Compose behavior unchanged. Set `restart: unless-stopped` for the persistent `database`, `ollama`, `api`, `worker`, and `caddy` services in the Azure overlay so they recover after VM reboot; do not apply restart policies to the one-shot model-pull jobs.

- [ ] **Step 4: Restrict proxy trust and preserve per-client demo limits**

In the Azure overlay, attach API to both its normal Compose network and a dedicated proxy network, attach Caddy only to the proxy network, and give the proxy network a fixed subnet and Caddy address `172.30.0.2`. Configure the Azure-only API Uvicorn command to trust forwarded headers only from `172.30.0.2`. Configure Caddy to replace/append forwarded-client headers correctly. Do not trust arbitrary forwarded headers from external clients; validate the subnet does not overlap the VM's VNet or existing Docker networks before startup.

- [ ] **Step 5: Validate deployment templates without provisioning**

Run `az bicep build --file documind/infra/main.bicep` and, with placeholder required Compose values, `docker compose -f documind/compose.yaml -f documind/compose.azure.yaml config -q`. Inspect the normalized overlay: Caddy alone publishes 80/443, API is not publicly published, PostgreSQL/Ollama have no host ports, and the three application named volumes remain declared.

---

### Task 3: Add a verified Entra owner-link operation and deployment runbook

**Files:**
- Create: `documind/src/documind/link_entra_identity.py`
- Create: `documind/tests/test_link_entra_identity.py`
- Create: `documind/docs/azure-vm-deployment.md`
- Modify: `documind/README.md`
- Modify: `documind/docs/architecture.md`

**Interfaces:**
- Consumes: An existing local user ID, one verified Entra identity tuple `(issuer, subject)`, and the initialized application database.
- Produces: A one-time, transactional CLI operation that links the Entra identity to the existing local user without copying document contents or creating a second workspace owner.

- [ ] **Step 1: Test the one-time identity-link operation**

Add tests proving the operation links the specified verified external identity to the existing local user, preserves workspace memberships, is idempotent for the same mapping, and refuses an unknown local user. If Entra sign-in has already auto-created an empty user, allow relinking only when that user has no memberships, owned data, or other external identities; refuse all other conflicting mappings. It must not accept an unverified email address as identity proof.

- [ ] **Step 2: Implement the CLI operation**

Implement `python -m documind.link_entra_identity --local-user-id <id> --issuer <issuer> --subject <subject>` using the existing SQLAlchemy models and one database transaction. Require the operator to obtain issuer and subject from a successful Entra sign-in recorded by the application; do not log access tokens or put identity values in tracked config. The operation has no recurring Azure service cost.

- [ ] **Step 3: Document Azure setup and the HTTPS/Entra prerequisite**

In `azure-vm-deployment.md`, document Azure DNS-label HTTPS via Caddy certificate automation, manual Entra SPA redirect URI update to `https://<dns-label>`, VM and SSH prerequisites, Azure-only Compose startup, secret handling, backup/restore, health checks, rollback, and the explicit cleanup gate. State that if certificate issuance or Entra redirect cannot be completed without buying a domain, public rollout stops at that gate.

- [ ] **Step 4: Document that Azure consumes student credit continuously**

Update README and architecture deployment notes: the always-on VM uses compute credit continuously; managed disk and static IP costs continue while deallocated; budget alerts are notifications rather than hard caps; do not expose plain HTTP sign-in. Do not change local Compose default behavior.

- [ ] **Step 5: Run focused verification**

Run `python -m pytest documind/tests/test_link_entra_identity.py -q`, `az bicep build --file documind/infra/main.bicep`, both local and Azure Compose config validation, and `git diff --check`.

---

### Task 4: Provision the authorized VM and transfer the existing environment

**Files:**
- Operational use of: `documind/infra/main.bicep`, `documind/infra/cloud-init.yaml`, `documind/compose.azure.yaml`, and `documind/docs/azure-vm-deployment.md`
- No credentials, backups, or generated deployment state committed to the repository.

**Interfaces:**
- Consumes: Task 1 approval, validated configuration from Task 2, the user's SSH key, Entra tenant/app settings, local PostgreSQL database, uploads volume, and Ollama model volume.
- Produces: An Azure VM running the same Compose application and restored persistent data, initially retained alongside the untouched local source.

- [ ] **Step 1: Run Bicep what-if and review network changes**

Run an Azure deployment `what-if` in the approved resource group/region. Verify only the planned VM, OS disk, VNet/subnet, NIC, NSG, and public IP will be created or changed. Ask for explicit confirmation immediately before applying the deployment.

- [ ] **Step 2: Provision the VM and verify secure access**

Apply the approved Bicep deployment only after that confirmation. Verify SSH works from the allowed administrative IP and externally only ports 80/443 are open. Confirm cloud-init installed Docker and Compose successfully.

- [ ] **Step 3: Create a consistent local backup**

Schedule a migration window; stop local API and worker writes, create a PostgreSQL logical dump while PostgreSQL is running, then stop PostgreSQL and Ollama before archiving `documind-uploads` and `documind-models` volumes. Record database table counts and an uploaded-file SHA-256 manifest, then restart local services only if needed. Store archives outside the repository and keep the recovery VHDX unchanged. Create a source archive from the exact current `documind` worktree, including intended uncommitted changes but excluding `.env`, `.git`, `node_modules`, `.venv`, and build output; do not require a Git commit or push.

- [ ] **Step 4: Transfer and restore the data**

Copy the application source archive and data archives to the VM over SSH. Restore the database dump into PostgreSQL 16, restore upload and Ollama model volume contents to the existing named volumes, set the untracked Azure `.env`, then start with `docker compose -f compose.yaml -f compose.azure.yaml up --build -d`. Confirm Ollama reports both `nomic-embed-text` and `granite3.3:2b`.

- [ ] **Step 5: Compare restored data before public cutover**

Compare database table counts and upload-file SHA-256 values with the source manifest. Verify the database's stored embedding model ID matches the restored Ollama model and do not re-index if the exact model was restored. If hashes/counts/model ID differ, stop and restore again; do not clean local data.

---

### Task 5: Enable HTTPS demo access and verify private Entra workspaces

**Files:**
- Operational use of: `documind/infra/Caddyfile`, `documind/compose.azure.yaml`, `documind/docs/azure-vm-deployment.md`
- Modify: Entra app registration redirect URI and deployment-only `.env` values through the owner's secure portal/environment
- No client secret in frontend build arguments or browser assets.

**Interfaces:**
- Consumes: Restored Azure deployment, Azure DNS hostname, and verified Entra SPA/API registration settings.
- Produces: Public synthetic demo on HTTPS, Entra-authenticated private workspace access, and a verified rollback point.

- [ ] **Step 1: Obtain a valid HTTPS certificate**

Point Caddy at the Azure public IP DNS label and start the proxy. Verify certificate issuance and browser trust at `https://<dns-label>`. If certificate issuance fails or requires a purchased domain, stop public rollout; do not serve Entra sign-in over HTTP.

- [ ] **Step 2: Configure Entra redirect and application values**

In the Entra app registration, add the exact HTTPS SPA redirect URI and configure the existing tenant/client/API audience/scope values in the untracked VM environment and Compose build settings. Rebuild the browser after the values are confirmed.

- [ ] **Step 3: Link the existing local owner to Entra**

Sign in to the Azure deployment with the intended Entra account, identify the resulting verified `(issuer, subject)` from the application database, then run the one-time link command from Task 3 against the existing local owner user ID. Verify that the account can list and access its previous authorized workspaces and that a different Entra identity cannot.

- [ ] **Step 4: Verify the full public and private user journeys**

Verify the synthetic public demo exists (seed it only if absent), lists only its fixed workspace, and answers only from synthetic documents; verify private sign-in, document listing, upload/indexing, and question/citation behavior. Check that separate client IPs have independent rate-limit buckets and that a forged incoming `X-Forwarded-For` cannot spoof a client; verify `/health/ready` and that direct public access to ports 8000, 5432, and 11434 is blocked.

- [ ] **Step 5: Reboot and confirm persistence**

Restart the VM, verify Docker Compose services recover, the Caddy certificate persists, the database/uploads/models remain present, and public/private user journeys still pass. Create and test an Azure-side PostgreSQL backup and retain the local recovery copy.

---

### Task 6: Cut over, monitor credit, and keep the local rollback intact

**Files:**
- Modify: `documind/docs/azure-vm-deployment.md`

**Interfaces:**
- Consumes: Successful Task 5 verification and the user's intended public demo URL.
- Produces: Documented operating, backup, credit monitoring, rollback, and shutdown procedures.

- [ ] **Step 1: Record cutover and recovery details**

Document the Azure resource names, region, VM SKU, public HTTPS URL, Compose commands, backup location/retention, SSH restriction, and how to switch back to local service. Do not include subscription secrets, passwords, API keys, or Entra tokens.

- [ ] **Step 2: Monitor actual credit consumption**

Compare Azure Cost Management actual charges/credit balance after the VM has run. Configure budget notifications if available and document that notifications are not a spending cap. If projected costs exceed remaining student credit, deallocate the VM and inform the user that always-on availability is not feasible within the limit.

- [ ] **Step 3: Verify the rollback path**

Confirm the local stack and recovery backup remain available until the user signs off. Document rollback as returning the owner to the preserved local development stack; the public Azure demo may be offline during rollback because no custom domain or public tunnel is in scope. Do not overwrite local volumes during Azure testing.

---

### Task 7: Remove local DocuMind data only after separate approval

**Files:**
- Operational use of: `documind/docs/azure-vm-deployment.md`
- No unrelated Docker project or recovery-backup files may be removed.

**Interfaces:**
- Consumes: Successful Azure verification/reboot, verified Azure-side backup, and a fresh explicit user approval for local cleanup.
- Produces: Reclaimed local Docker storage for DocuMind while preserving the recovery VHDX backup and unrelated Docker projects/data.

- [ ] **Step 1: Reconfirm exact local targets and approval**

Inspect Docker references before removal. Present the exact DocuMind containers, images, and volumes to be deleted, plus the expected reclaimable space. Require a separate user confirmation; if any object is shared with another project, omit it unless the user approves its removal.

- [ ] **Step 2: Remove only approved DocuMind objects**

Stop the DocuMind Compose project, remove its database, uploads, and Ollama model volumes and DocuMind/Ollama images; remove the pgvector image only if Docker inspection confirms no other project uses it. Do not run `docker compose down -v`, `docker system prune`, or delete other project resources. Preserve `D:\\DockerDesktopRecovery-20261102\\docker_data.vhdx`.

- [ ] **Step 3: Compact Docker storage safely**

Use Docker Desktop/WSL's supported VHDX compaction procedure only after Docker has stopped cleanly. Verify the active VHDX path before compacting, never target the recovery backup, and re-check C:/D: free space and `docker system df` afterward.
