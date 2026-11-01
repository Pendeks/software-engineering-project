# Engineering Portfolio

This workspace is the foundation for a 26-week engineering portfolio built around three production-style projects:

- FlowDesk — SaaS team collaboration and project management platform
- DocuMind — AI document intelligence with RAG
- DeployFlow — CI/CD and cloud deployment operations platform

## Portfolio objective

The goal is to demonstrate practical engineering ability across:

- Full-stack development
- Backend and REST API design
- Frontend architecture with React/Next.js
- PostgreSQL and database modeling
- Authentication and authorization
- Azure cloud engineering
- Docker and container workflows
- GitHub Actions and CI/CD
- Infrastructure as Code
- AI and LLM integration
- Security, testing, observability, and troubleshooting

## Workspace structure

```text
software-engineering-project/
├── README.md
├── docs/
│   ├── roadmap.md
│   ├── repository-standards.md
│   ├── azure-planning.md
│   └── portfolio-dashboard.md
├── flowdesk/
├── documind/
├── deployflow/
└── screenshots/
```

## Project roadmap

See [docs/roadmap.md](docs/roadmap.md) for the full 26-week plan and milestones.

## Current status

- Current week: 16 of 26
- Current phase: DeployFlow — continuous integration
- FlowDesk status: Weeks 2-8 complete. The temporary public demo uses a direct Node.js deployment on Linux App Service F1 in Indonesia Central; a local Docker image is built and verified separately.
- Implemented: Demo authentication, Admin/Manager/Member/Viewer authorization with project scoping, separate login and dashboard pages, project and task management, search, status filtering, comments, and theme switching.
- Current prototype stack: TypeScript, Express, plain HTML/CSS/JavaScript, in-memory data, and Docker for local runs.
- Validation: FlowDesk tests pass; production dependency audit reports zero vulnerabilities; local Docker image and readiness endpoint verified. Stored-XSS fix deployed to the demo; Chrome Safe Browsing clearance remains unconfirmed.
- Live demo: [FlowDesk sign-in](https://flowdesk-demo-399203.azurewebsites.net/)
- DocuMind: Local API, worker, database, and browser app implemented and run with Docker Compose; live Azure model-backed processing is blocked by the Azure for Students subscription's allowed-region policy.
- Next milestone: GitHub Actions CI for FlowDesk and DocuMind, followed by DeployFlow Docker and registry work.

## Execution approach

1. Define standards and engineering conventions
2. Scaffold the repository layout for each project
3. Complete project foundation and architecture docs
4. Build core functionality iteratively by week
5. Deploy, monitor, and document each solution

## Notes

- Production Azure resources should only be deployed during each project’s deployment phase.
- The focus is on demonstrating engineering depth and risk-aware implementation, not expensive cloud sprawl.
- Sensitive credentials, document content, and secrets must never be committed to source control.
