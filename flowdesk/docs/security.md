# FlowDesk Security Notes

## Security objectives

FlowDesk should demonstrate a realistic security posture for a SaaS product, especially around authentication, authorization, data handling, and safe deployment.

## Key controls

- Protected routes and server-side role/project-scope enforcement for the seeded demo identities
- Input validation and sanitization for all user data
- Structured audit logging for sensitive actions
- Secure handling of environment variables and deployment secrets

The public demo intentionally uses static plaintext credentials and bearer tokens. This is suitable only for non-sensitive demonstrations; replace it with password hashing and revocable, expiring sessions before production use.

## 2026-11-01 stored XSS remediation

The security review found that project names and owners, task titles and assignees, statuses, and comments were interpolated into dashboard HTML. Since authenticated demo users can submit some of these values, crafted content could execute as stored cross-site scripting when another user viewed the affected project or task.

The dashboard now HTML-escapes dynamic text and attribute values before inserting them into its templates. A regression test checks escaping of HTML metacharacters and verifies that project, task, and comment rendering use the escaping helper. The FlowDesk test suite passed after the change.

The same deployment surfaced two production dependency advisories: a high-severity `body-parser` denial-of-service advisory and a moderate `qs` denial-of-service advisory. Compatible dependency updates were applied; `npm audit --omit=dev` reported zero vulnerabilities, and the application was redeployed with the updated lockfile.

The updated application was deployed to the temporary Azure App Service on 2026-11-01. Deployment health and readiness checks returned HTTP 200. This does not confirm that Chrome Safe Browsing has cleared its warning; check the site status through the appropriate Google Search Console/Safe Browsing review process before sharing the demo, and do not bypass a browser warning or use the demo with sensitive data.

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
