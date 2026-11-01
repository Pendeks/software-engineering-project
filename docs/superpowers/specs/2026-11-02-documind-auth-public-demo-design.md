# DocuMind Authentication and Public Demo Design

**Status:** Draft for approval

## Intent

Replace DocuMind's shared bearer token for private workspaces with per-user sign-in, while giving recruiters an easy way to try the product without a college account. Keep both experiences in the existing application.

## Goals

- Require Microsoft Entra ID sign-in for private workspace and document APIs.
- Identify users by a stable provider identity, not email address, and apply existing workspace membership checks to that user.
- Offer a no-login, read-only demo containing synthetic documents only.
- Keep local development usable with the current bearer-token flow, but never accept that token in the deployed OIDC mode.
- Preserve the current local storage interface; Azure Blob Storage is a separate later milestone.

## Non-goals

- Public access to private workspaces, uploads, document mutations, or processing controls.
- Recruiter accounts, invitations, multiple identity providers, or multi-tenant private sign-in.
- Migration or automatic ownership transfer of existing local documents into a signed-in account.
- Azure Blob Storage integration, production hosting setup, or tenant/app registration.

## Constraints and prerequisites

- The application is a React/Vite SPA backed by FastAPI. Today the SPA accepts a bearer token in memory; the API maps one configured token to one user ID.
- Workspaces already have user memberships, and routes check membership server-side.
- Original files use a `put`/`read`/`delete` storage interface with local filesystem storage. Blob Storage is already an architecture direction but is not part of this design.
- The user is unsure whether they can register an application in the intended Azure tenant. Entra app registration and any required consent are external prerequisites. Do not attempt tenant changes. If registration is unavailable, pause private OIDC implementation and ask the user to choose an identity provider they can use.
- Repository inspection found no existing demo workspace, demo fixture, or seed files. The implementation therefore needs to create and verify a deterministic synthetic demo dataset.
- Local bearer-token mode remains restricted to local development configuration. Deployed OIDC mode must fail closed if required identity settings are missing.

## Approaches

1. **One application with separate private and public-demo paths (selected).** Entra ID protects all private routes; dedicated demo routes expose only a configured sample workspace. This keeps operating cost and deployment count low, while requiring strong separation tests.
2. **Separate demo deployment and sample-only database.** This gives stronger infrastructure isolation, but adds deployment and maintenance overhead that the initial portfolio demo does not justify.
3. **Require Microsoft sign-in for recruiters.** This avoids anonymous access, but conflicts with the goal of an easy public demo for recruiters outside the college.

## Design

### Private sign-in

- The browser uses the Microsoft Authentication Library (MSAL) authorization-code flow with PKCE. Access tokens remain in memory and are cleared on sign-out; do not put tokens in local storage.
- The API accepts bearer access tokens only in OIDC mode and validates signature, issuer, audience, expiry, and the configured tenant using Entra's published signing keys.
- Map the validated `(issuer, subject)` pair to an internal `User.id` through a unique identity record. Do not use email, display name, or a client-supplied user ID as the account key.
- Continue using the existing workspace membership check after authentication. A valid login alone must not grant access to a workspace.
- Keep the existing bearer-token flow available only in local development mode. Never silently fall back from OIDC to the shared token.
- Existing local data remains owned by its current local user. Do not automatically link it to an Entra account; any future data transfer needs an explicit, reviewed migration.

### Public recruiter demo

- Add a separate unauthenticated demo experience and dedicated demo API operations for listing the configured sample workspace's documents and asking questions against its ready documents.
- The demo workspace identifier is configured server-side. The client cannot choose an arbitrary workspace ID to enter the public path.
- Seed the demo with synthetic, non-sensitive documents only. Demo responses and citations must resolve only to documents in that workspace.
- Demo routes are read-only: they cannot create or list general workspaces, upload, delete, retry processing, or access private routes without a valid Entra token.
- Apply a request limit to unauthenticated demo operations and return an explicit rate-limit response. Do not rely on the client to enforce limits.

### Files and interfaces expected to change

- `documind/src/documind/api.py`: separate OIDC and demo authentication/authorization dependencies; keep membership checks for private routes.
- `documind/src/documind/config.py` and `documind/.env.example`: explicit local/OIDC mode and required Entra issuer, tenant, and audience configuration; demo workspace and request-limit settings.
- `documind/src/documind/models.py` and `documind/src/documind/database.py`: add an identity mapping keyed by issuer and subject, with a foreign key to the existing user record.
- `documind/web/src/App.tsx` and `documind/web/src/api.ts`: replace production token entry with sign-in/sign-out and add the public demo entry point.
- `documind/tests/test_documents.py` plus focused frontend tests: prove OIDC validation, authorization isolation, demo read-only behavior, and preservation of local mode.
- `documind/README.md` and `documind/docs/architecture.md`: document local setup, Entra prerequisites, demo data rules, and the local-only limitation.

Exact implementation signatures and test cases belong in the implementation plan after this design is approved.

## Security and failure behavior

- Missing or invalid tokens, wrong issuer/audience/tenant, expired tokens, unknown signing keys, and disabled/misconfigured OIDC must not grant access.
- A user from another workspace must not retrieve its documents, chunks, or citations, including through the public demo routes.
- A demo question must not retrieve non-demo workspace content, even if a caller supplies another workspace identifier.
- Missing Entra configuration must produce a clear startup/configuration failure in OIDC mode, not a local-token fallback.
- Rate limiting applies on the server to unauthenticated demo API calls.

## Acceptance criteria

1. In local development mode, the existing bearer-token workflow continues to work.
2. In OIDC mode, a valid Entra token maps consistently to one internal user; invalid, expired, wrong-tenant, wrong-issuer, or wrong-audience tokens are rejected.
3. Private workspace routes still require membership; authentication alone does not grant cross-workspace access.
4. A recruiter can open the demo without an account, inspect only synthetic sample documents, and receive answers whose citations name only those sample documents.
5. Anonymous demo requests cannot mutate data or access arbitrary workspaces; excessive requests receive a server-generated rate-limit response.
6. No app registration, tenant, Azure resource, or secret is created or changed by this code work.
7. Azure Blob Storage remains a separate follow-up design and is not required for this milestone.

## Calls left to the implementer

- Choose the smallest compatible Python JWT/JWKS validation library and MSAL package versions without broad dependency upgrades.
- Choose a deterministic synthetic demo fixture that answers at least one verifiable question.
- Set a conservative initial demo request limit and document how to tune it; revisit distributed rate limiting before scaling beyond one application instance.

## Builder check

- Entra app registration and consent remain unknown. Treat them as an external prerequisite; do not make tenant changes or proceed with production OIDC configuration until availability is confirmed.
- No demo workspace or synthetic dataset exists in the repository. Create the fixture and configure the public demo workspace as part of implementation.
