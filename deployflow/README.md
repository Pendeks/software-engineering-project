# DeployFlow

## Overview

DeployFlow is a cloud and DevOps deployment platform designed to demonstrate CI/CD, infrastructure provisioning, application deployment, health checks, monitoring, and recovery workflows.

## Core goals

- Show automated CI validation
- Build a production container image
- Publish images to a registry
- Provision Azure infrastructure as code
- Deploy application updates safely
- Implement health checks and rollback readiness
- Demonstrate security and operational maturity

## Planned technology stack

- GitHub Actions
- Docker
- Azure Container Registry
- Azure App Service or container hosting
- Bicep or Terraform
- Azure Monitor
- GitHub and branch protection flows

## Planned milestones

- CI
- Production pipeline
- Deployment automation and reliability

## Continuous integration

The repository's GitHub Actions workflow is [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml). It runs on pushes and pull requests that change FlowDesk or DocuMind, and can also be started manually.

The independent jobs run FlowDesk's build and smoke tests plus a production dependency audit, DocuMind's Python API and processing tests, and the DocuMind web dependency audit and production build. Each job uses a least-privilege read-only repository token. CI does not deploy to Azure, publish images, or require cloud secrets.

While validating the web build for CI, the dependency audit identified a high-severity Vite advisory. The lockfile now resolves Vite 6.4.5, and the full web dependency audit reports zero vulnerabilities.

To run the same checks locally:

```powershell
Push-Location ..\flowdesk
npm ci
npm test
npm audit --omit=dev
Pop-Location

Push-Location ..\documind
python -m pip install -e ".[test]"
python -m pytest
Pop-Location

Push-Location ..\documind\web
npm ci
npm run build
Pop-Location
```

## Project docs

Planned documentation includes:

- CI workflow
- Infrastructure as code
- Deployment procedures
- Health checks
- Troubleshooting and rollback guide
- Security review

## Notes

This project is intended to demonstrate the software delivery lifecycle in a way that is understandable to recruiters and technical reviewers.
