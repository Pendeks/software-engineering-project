# DocuMind Authentication and Public Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user Entra sign-in for private DocuMind workspaces and a no-login, read-only recruiter demo backed only by deterministic synthetic content.

**Architecture:** Keep one deployment. The API validates Entra access tokens and maps the stable `(issuer, subject)` identity pair to an internal user before applying existing workspace membership checks. Add dedicated demo endpoints pinned to one configured workspace, seed that workspace with synthetic documents, and make the browser offer private sign-in or a separate public demo experience.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic Settings, PyJWT with cryptographic/JWKS support, React 19, TypeScript, MSAL React/Browser, pytest, Vitest, React Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-02-documind-auth-public-demo-design.md`

## Global Constraints

- Require Microsoft Entra ID sign-in for private workspace and document APIs.
- Identify users by a stable provider identity, not email address, and apply existing workspace membership checks to that user.
- Offer a no-login, read-only demo containing synthetic documents only.
- Keep local development usable with the current bearer-token flow, but never accept that token in the deployed OIDC mode.
- Preserve the current local storage interface; Azure Blob Storage is a separate later milestone.
- Do not automatically link existing local data to an Entra account.
- The demo workspace identifier is configured server-side; the client cannot choose an arbitrary workspace ID to enter the public path.
- Demo routes are read-only: they cannot create or list general workspaces, upload, delete, retry processing, or access private routes without a valid Entra token.
- Missing Entra configuration must produce a clear startup/configuration failure in OIDC mode, not a local-token fallback.
- Do not create or change an app registration, tenant, Azure resource, or secret in code work.
- Entra app-registration availability is unknown. Stop before implementing private OIDC and ask the user to confirm registration/consent access; do not assume it is available.
- The user handles all commits and pushes; do not create commits or push.

## Review Focus

- Missing Entra settings or malformed, expired, wrong-issuer, wrong-audience, wrong-tenant, or unknown-key tokens must fail closed — pin in Task 1 tests.
- Existing local workspace memberships and content must not be silently reassigned to a new Entra identity, and a valid new login must not bypass membership checks — pin in Task 1 identity/membership tests.
- A caller-supplied workspace/document identifier must never escape the configured demo workspace, including through question retrieval and citations — pin in Task 2 endpoint tests.
- A missing or conflicting demo workspace/fixture must fail explicitly rather than expose arbitrary existing content or claim seeding succeeded — pin in Task 2 seed-command tests.
- Public request limits must use a server-controlled client address and return a clear `429` without trusting an arbitrary forwarded-address header — pin in Task 2 rate-limit tests.

---

## File Structure

- Create `documind/src/documind/auth.py` for Entra JWT/JWKS validation and stable external-identity resolution.
- Modify `documind/src/documind/config.py`, `models.py`, `database.py`, `api.py`, and `pyproject.toml` for explicit auth mode, identity persistence, private auth, and demo API wiring.
- Create `documind/src/documind/demo_content.py` and `seed_demo.py` for deterministic, synthetic demo content and an idempotent provisioning command.
- Create `documind/tests/test_auth.py` and `test_demo.py`; retain `test_documents.py` for local-token and existing workspace regression coverage.
- Modify `documind/.env.example`, `README.md`, and `docs/architecture.md` to document local/OIDC modes, the external Entra prerequisite, demo seeding, demo restrictions, and the later Blob Storage milestone.
- Modify `documind/web/package.json` and its npm lockfile to add MSAL and focused frontend-test dependencies.
- Create `documind/web/src/auth.ts` for MSAL initialization and access-token acquisition; modify `main.tsx`, `App.tsx`, `api.ts`, and the existing `vite.config.ts` for sign-in, API calls, demo entry, and test configuration.
- Create `documind/web/src/App.test.tsx` and/or `api.test.ts` for mode and demo behavior; add the Vitest configuration needed to run them.

## Task 1: Entra Configuration, Identity Mapping, and API Authentication

**Files:**
- Create: `documind/src/documind/auth.py`
- Modify: `documind/src/documind/config.py`
- Modify: `documind/src/documind/models.py` and `database.py`
- Modify: `documind/src/documind/api.py`
- Modify: `documind/pyproject.toml`
- Test: `documind/tests/test_auth.py`
- Test: `documind/tests/test_documents.py`

**Interfaces:**
- `Settings.auth_mode: Literal["local", "entra"]`, defaulting to `"local"` for the local Compose/development topology.
- `Settings.entra_tenant_id: str | None`, `Settings.entra_client_id: str | None`, and `Settings.entra_api_audience: str | None`; OIDC mode requires all three.
- `ExternalIdentity` stores a composite primary key `(issuer, subject)` and a foreign key `user_id` to `users.id`; do not store email as an identity key.
- `verify_entra_access_token(token: str, settings: Settings) -> tuple[str, str]` returns validated `(issuer, subject)` after signature, exact issuer, audience, expiry, tenant, and required-claim validation.
- `get_or_create_external_user(session: Session, issuer: str, subject: str) -> str` returns a stable internal user ID and commits a new identity/user mapping safely.
- `current_user` keeps returning the internal `User.id` consumed by existing routes; local mode preserves the configured token-subject behavior.

- [ ] **Step 1: Confirm the external Entra prerequisite before private OIDC implementation.**

Ask the user whether they can register a single-tenant Entra application and grant its required consent. The selected implementation assumes one registration provides a SPA redirect URI and an API scope; collect the tenant ID, client ID/API audience, and API scope only when the user confirms access. If availability is still unknown or unavailable, stop this task before implementation and ask the user to choose how to proceed. Do not access or modify tenant settings.

- [ ] **Step 2: Write failing tests for auth mode configuration and identity validation.**

Add tests named `test_entra_mode_requires_tenant_client_and_audience`, `test_local_mode_preserves_token_authentication`, `test_entra_mode_rejects_local_token_without_access_token`, `test_entra_token_rejects_invalid_signature`, `test_entra_token_rejects_wrong_tenant_issuer_audience_expiry_and_unknown_key`, `test_entra_token_maps_same_issuer_subject_to_same_user`, `test_identity_mapping_does_not_transfer_existing_local_memberships`, `test_entra_identity_still_requires_workspace_membership`, and `test_entra_mode_rejects_anonymous_private_mutations`. Generate test signing keys locally and stub the JWKS client; tests must not call Entra or use real credentials.

- [ ] **Step 3: Run the focused tests and verify they fail for the missing implementation.**

Run from `documind\`: `python -m pytest tests/test_auth.py tests/test_documents.py -q`
Expected: new tests fail because auth settings, identity model, or validation behavior is not implemented; pre-existing tests remain collected.

- [ ] **Step 4: Add auth settings, the identity model, and the PyJWT dependency.**

Add PyJWT with cryptographic/JWKS support using a compatible bounded version range in `pyproject.toml`. Validate required Entra settings when `auth_mode == "entra"`; do not use a local-token fallback in that mode. Add the composite-key `ExternalIdentity` model referencing `User.id`.

- [ ] **Step 5: Implement token validation and identity resolution in `auth.py`.**

Use the configured tenant's v2 issuer and JWKS endpoint; accept only the expected signing algorithm, require `iss`, `sub`, `tid`, `aud`, and `exp`, compare issuer/audience/tenant exactly, and use the issuer-subject pair for lookup. Create new internal IDs with `uuid4().hex`, which fits `User.id`'s current `String(64)`. Do not trust email, display name, or client-supplied IDs.

- [ ] **Step 6: Wire authentication into `api.py` and run the focused tests.**

Keep all existing private endpoints dependent on `current_user` and preserve `require_workspace_member`. In local mode, retain the shared bearer-token behavior. In Entra mode, validate an access token and resolve its internal user ID; reject old local tokens even if `api_token` is configured. Run `python -m pytest tests/test_auth.py tests/test_documents.py -q`.
Expected: all selected tests pass, including existing private-workspace isolation tests.

## Task 2: Synthetic Demo Workspace, Read-Only API, and Server Rate Limit

**Files:**
- Create: `documind/src/documind/demo_content.py`
- Create: `documind/src/documind/seed_demo.py`
- Modify: `documind/src/documind/config.py`
- Modify: `documind/src/documind/api.py`
- Modify: `documind/src/documind/models.py` and `database.py`
- Test: `documind/tests/test_demo.py`

**Interfaces:**
- `Settings.demo_workspace_id: str | None` identifies the one server-configured workspace exposed by the demo.
- `Settings.demo_rate_limit_requests: int = 30` and `Settings.demo_rate_limit_window_seconds: int = 60` define the initial per-process limit.
- `Workspace.is_public_demo: bool = False` marks a workspace as intentionally designated for public demo access; the demo seeder is the only code path that sets it to `True`.
- `GET /api/v1/demo/documents` returns `list[DocumentResponse]` for the configured workspace only.
- `POST /api/v1/demo/questions` accepts the existing `QuestionRequest` and returns `QuestionResponse` for that configured workspace only.
- Demo operations do not accept a workspace ID from the caller and do not require private user authentication.
- `python -m documind.seed_demo` idempotently creates the configured synthetic workspace, documents, versions, and processing jobs, and fails explicitly on conflicting pre-existing data.

- [ ] **Step 1: Write failing tests for the pinned demo boundary and seed behavior.**

Add tests named `test_demo_lists_only_configured_workspace_documents`, `test_demo_question_citations_are_limited_to_demo_workspace`, `test_demo_ignores_arbitrary_workspace_ids_and_has_no_mutation_routes`, `test_demo_requires_a_marked_workspace`, `test_demo_is_unavailable_without_workspace_configuration`, `test_demo_seed_is_idempotent`, and `test_demo_seed_refuses_an_existing_private_workspace`. The synthetic fixture must contain the sentence `The Aurora archive keeps its emergency lantern amber.`; ask `What color is the emergency lantern?` and assert the fake provider answer is `The emergency lantern is amber [1].` with a citation to `recruiter-demo-handbook.txt`. Use the existing fake embedding/chat providers and SQLite test setup; prove a private document's content and citation cannot appear in demo responses.

- [ ] **Step 2: Run the demo tests and verify the missing routes/seed fail.**

Run from `documind\`: `python -m pytest tests/test_demo.py -q`
Expected: new tests fail because demo configuration, routes, and seed command do not yet exist.

- [ ] **Step 3: Add deterministic synthetic fixture content and the idempotent seed command.**

Include a small synthetic handbook with the exact sentence and question/answer from Step 1. Require `demo_workspace_id` for seeding; create no content in any other workspace. Mark only the seeded workspace `is_public_demo=True`; refuse to repurpose an existing unmarked workspace, including one whose ID matches the configured value. Add a backward-compatible `initialize_schema` migration that adds `workspaces.is_public_demo BOOLEAN NOT NULL DEFAULT FALSE` to existing SQLite and PostgreSQL databases, leaving every existing workspace private. Create the internal fixture owner and document/version/queued-job rows consistently with the existing schema, store originals through `LocalFileStorage`, and let the existing worker index them. Re-running must not duplicate documents or overwrite conflicting content.

- [ ] **Step 4: Implement fixed-workspace demo endpoints and rate limiting.**

Query documents and call `answer_question` using only `Settings.demo_workspace_id` and `Workspace.is_public_demo is True`; do not accept workspace IDs in the request or invoke private workspace listing. If the demo workspace ID is absent, return an explicit `503`; if the configured workspace is absent or not marked public, return an explicit unavailable response without exposing its contents. Add an in-process fixed-window limit of 30 requests per 60 seconds per `request.client.host` for both demo endpoints, return HTTP `429` with `Retry-After`, prune expired client buckets so state is bounded to active windows, and do not trust `X-Forwarded-For`. Keep the limit explicitly documented as single-process; behind a reverse proxy, configure trusted-proxy client address handling before exposure, and require a shared limiter before scaling to multiple API processes/instances.

- [ ] **Step 5: Test request limits and run all demo tests.**

Add `test_demo_rate_limit_returns_429_and_retry_after`, `test_demo_rate_limit_ignores_untrusted_forwarded_for`, and `test_existing_workspaces_remain_unmarked_after_schema_upgrade`. Use a controllable clock or a test-specific small limit rather than sleeping. Run `python -m pytest tests/test_demo.py -q`.
Expected: demo listing/questioning is public but only for the marked configured workspace, mutations remain unavailable anonymously, seed conflicts are explicit, existing workspaces stay private after schema upgrade, and the 31st request within a 60-second window from one client address receives `429`.

## Task 3: MSAL Private Sign-In and Separate Public Demo Experience

**Files:**
- Modify: `documind/web/package.json` and the npm lockfile
- Create: `documind/web/src/auth.ts`
- Modify: `documind/web/src/main.tsx`
- Modify: `documind/web/src/api.ts`
- Modify: `documind/web/src/App.tsx`
- Modify: `documind/web/vite.config.ts`
- Create: `documind/web/src/App.test.tsx`
- Create: `documind/web/src/api.test.ts`

**Interfaces:**
- Build-time settings: `VITE_DOCUMIND_AUTH_MODE`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_CLIENT_ID`, `VITE_ENTRA_API_SCOPE`, and `VITE_ENTRA_REDIRECT_URI`; no client secret is used in the SPA.
- `auth.ts` exports the MSAL `PublicClientApplication` configuration and an access-token acquisition function that returns an in-memory access token for the configured API scope.
- `api.ts` exports `request<T>(path: string, accessToken?: string, init?: RequestInit): Promise<T>`; it adds an Authorization header only when a token is provided.
- `App.tsx` offers private sign-in or “Try the demo”; demo view can list documents and ask questions but contains no workspace, upload, delete, or retry controls.

- [ ] **Step 1: Add focused frontend test tooling and write failing UI/API tests.**

Add MSAL Browser and MSAL React as runtime dependencies, and Vitest, jsdom, and React Testing Library as development dependencies. Add `npm test` and tests named `renders_sign_in_and_demo_choices_in_entra_mode`, `private_workspace_uses_acquired_access_token`, `demo_lists_and_questions_without_authorization_header`, `demo_view_has_no_mutation_controls`, `local_mode_retains_development_token_form`, and `production_build_requires_explicit_auth_mode`. Mock MSAL; do not use tenant credentials in tests.

- [ ] **Step 2: Run the frontend tests and verify they fail before implementation.**

Run from `documind\web\`: `npm test -- --run`
Expected: the new UI/API tests fail until the auth modes and demo view are implemented.

- [ ] **Step 3: Implement MSAL configuration and per-request token acquisition.**

Configure single-tenant authority from the build-time tenant ID, SPA client ID, redirect URI, and API scope. Use MSAL's in-memory cache; do not store tokens in local storage or persist a client secret. Surface sign-in/token acquisition errors in the existing UI error state.

- [ ] **Step 4: Update the API client and private UI for Entra and local modes.**

Use MSAL access tokens on private API requests in Entra mode, refresh/acquire them through MSAL as needed, and clear private workspace state on sign-out. Preserve the current token form only when `VITE_DOCUMIND_AUTH_MODE=local`; never show it as an OIDC fallback.

- [ ] **Step 5: Add the recruiter demo entry and read-only interface.**

Add a visible no-login demo entry from the landing experience. Render a separate demo mode that calls only `/api/v1/demo/documents` and `/api/v1/demo/questions`; send no Authorization header and show the citations returned by the API. Do not render private workspace mutation controls in this mode.

- [ ] **Step 6: Run frontend tests and production build.**

Run from `documind\web\`: `npm test -- --run` and `npm run build`.
Expected: all frontend tests pass and TypeScript/Vite production compilation succeeds.

## Task 4: Configuration, Operational Documentation, and End-to-End Acceptance

**Files:**
- Modify: `documind/.env.example`
- Modify: `documind/README.md`
- Modify: `documind/docs/architecture.md`
- Modify after acceptance: `docs/portfolio-dashboard.md`
- Test: `documind/tests/test_auth.py`
- Test: `documind/tests/test_demo.py`
- Test: `documind/tests/test_documents.py`
- Test: frontend test suite and production build

**Interfaces:**
- `.env.example` continues to show local mode by default and includes clearly named, empty Entra and demo settings.
- `README.md` documents the local token workflow, Entra registration/consent prerequisite, build-time SPA settings, demo seed command, worker indexing, rate-limit limitation, and no-secret policy.
- `docs/architecture.md` documents identity mapping, private membership enforcement, demo route boundary, synthetic-data requirement, and Blob Storage as a separate milestone.

- [ ] **Step 1: Document local mode, Entra setup requirements, and demo provisioning.**

Document that the deployment owner must separately register/configure the SPA and API scope and provide the client redirect URI; code work does not create registrations, consent, cloud resources, or secrets. Explain that private OIDC setup must pause until the user confirms access. Show how to set `DOCUMIND_AUTH_MODE=entra`, the required API values, the corresponding `VITE_` build values, run `python -m documind.seed_demo`, and allow the existing worker to index demo documents.

- [ ] **Step 2: Document the security and scale boundaries.**

State that only a workspace marked `is_public_demo` and containing synthetic documents is public; no uploads, mutations, private data, or cross-workspace retrieval are exposed. Document the 30-per-60-second per-process limit, trusted proxy address requirements, the single-process assumption, and the need for a shared limiter before scaling. Keep Azure Blob Storage, app registration, and production infrastructure setup out of implementation scope.

- [ ] **Step 3: Run the complete API and frontend validation.**

Run from `documind\`: `python -m pytest -q`
Run from `documind\web\`: `npm test -- --run` and `npm run build`
Expected: all API tests pass, frontend tests pass, and the production browser bundle builds.

- [ ] **Step 4: Verify the acceptance boundaries against the spec.**

Confirm automated tests establish: local bearer-token behavior remains available in local mode; OIDC invalid tokens and missing settings fail closed; an Entra identity maps consistently without changing existing local memberships; private routes still require workspace membership; demo documents/citations are synthetic and fixed-workspace only; anonymous mutations are impossible; and rate limiting returns `429`. After acceptance passes, update only the DocuMind status/outcome and next step in `docs/portfolio-dashboard.md`; do not invent schedule changes or mark the deployment complete before the user configures any external Entra prerequisite.
