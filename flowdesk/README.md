# FlowDesk

## Overview

FlowDesk is a production-style SaaS project management and team collaboration platform designed to demonstrate a realistic engineering stack and RBAC-heavy application architecture.

## Core goals

- Manage organizations, members, and roles
- Create and lead projects
- Track tasks from TODO to DONE
- Enable team collaboration with comments and notifications
- Showcase secure authentication and authorization patterns
- Provide a deployable application with monitoring and telemetry

## Current prototype stack

- TypeScript
- Express
- Plain HTML, CSS, and JavaScript
- Node.js
- In-memory demo data
- Docker

## Local run and verification

```sh
npm ci
npm run dev
```

The app listens on port 3000 by default. Set `PORT` to use a different port. Run `npm test` to build the TypeScript and execute the smoke tests.

### Run locally with Docker

From the `flowdesk` directory, build and start the container:

```powershell
docker build -t flowdesk:local .
docker run --name flowdesk-local -d -p 127.0.0.1:3001:3000 flowdesk:local
```

Open `http://127.0.0.1:3001/`. Check the container readiness at `http://127.0.0.1:3001/api/readyz` and view logs with `docker logs flowdesk-local`. Stop and remove the container with `docker rm -f flowdesk-local`; demo data is in memory and resets when the container stops.

The image runs as the non-root `node` user. This local Docker workflow is separate from the Azure demo deployment below, which currently uses a direct Node.js ZIP deployment on the F1 App Service plan.

## Deployment and observability

- `Dockerfile` builds and runs the app on Node.js 22, listens on port 3000, and runs as the non-root `node` user.
- Temporary live demo: [FlowDesk sign-in](https://flowdesk-demo-399203.azurewebsites.net/) — Azure App Service Linux F1 in Indonesia Central, using direct Node.js 22 LTS deployment.
- Azure resources are isolated in resource group `rg-flowdesk-demo`; the App Service plan is `asp-flowdesk-demo` and the web app is `flowdesk-demo-399203`.
- Redeploy with `.\deploy-azure.ps1` from PowerShell. The script builds the app, stages production dependencies, creates a Linux-compatible ZIP package, deploys it, and checks health and readiness.
- The 2026-11-01 security patch escapes user-controlled dashboard content and updates vulnerable production dependencies. See [Security Notes](docs/security.md) for the finding, verification, and deployment status.
- Chrome Safe Browsing status has not been confirmed after the patch. Do not bypass browser warnings or use the public demo with sensitive data.
- HTTPS-only access is enabled. App Service application and HTTP logs are configured to the filesystem at Information level.
- Operational review: a downloaded log sample contained 60 application request entries (40 HTTP 200 and 20 HTTP 304), with no logged errors or failed HTTP statuses. Fresh health and readiness probes both returned HTTP 200 and appeared in the application logs.
- `GET /api/health` reports service health and process uptime.
- `GET /api/readyz` is the container readiness probe.
- HTTP requests produce JSON logs on stdout with a request ID, method, path (without query parameters), status code, and duration. No authorization headers, bodies, or query values are logged.
- The sign-in page displays demo credentials. This is a public, temporary demo only; do not enter or store sensitive data. In-memory data resets when the app restarts.
- The live demo includes Admin, Manager, Member, and Viewer accounts to exercise role and project-scope rules; the credentials are public and must never be reused for real accounts.
- API authorization is enforced server-side: project data is scoped by role assignments, Members can edit only their own tasks, and Viewers are read-only. UI control visibility is only a convenience, not a security boundary.
- App Service F1 is the intended free tier; verify Azure for Students terms and remove the resource group when finished. No database, paid telemetry, or storage services were created.

## Project docs

This repository will eventually include:

- Requirements
- Architecture
- Database design
- API design
- Authentication and authorization docs
- Deployment guidance
- Security review
- Observability notes

## Notes

The project should focus on realistic production concerns, not only simple CRUD behavior. It should demonstrate role-based access control, auditability, operational observability, and secure deployment practices.
