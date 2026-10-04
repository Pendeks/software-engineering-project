# FlowDesk Security Notes

## Security objectives

FlowDesk should demonstrate a realistic security posture for a SaaS product, especially around authentication, authorization, data handling, and safe deployment.

## Key controls

- Protected routes and server-side role/project-scope enforcement for the seeded demo identities
- Input validation and sanitization for all user data
- Structured audit logging for sensitive actions
- Secure handling of environment variables and deployment secrets

The public demo intentionally uses static plaintext credentials and bearer tokens. This is suitable only for non-sensitive demonstrations; replace it with password hashing and revocable, expiring sessions before production use.

## Threats to address

- unauthorized access to organization data
- insecure user role assignment
- injection or malformed API input
- task or project manipulation by unauthorized users
- accidental disclosure of secrets in logs or screenshots

## Security review checklist

- test all role and project-scope boundaries before shipping a feature
- validate database queries for tenant scoping
- ensure logs omit sensitive values
- apply least privilege to Azure resources and deployment identities
- review third-party packages for outdated vulnerabilities

## Recommended future validation

- use automated API tests for permission boundaries
- add integration tests for auth flows and task mutations
- review app configuration before deployment to Azure
- keep dependency scanning and vulnerability checks in the CI process
