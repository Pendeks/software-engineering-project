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

- Current week: 9 of 26
- Current phase: DocuMind — AI architecture and pipelines
- FlowDesk status: Complete for Weeks 2-8; deployed as a temporary, non-containerized demo on Linux App Service F1 in Indonesia Central.
- Implemented: Demo authentication, Admin/Manager/Member/Viewer authorization with project scoping, separate login and dashboard pages, project and task management, search, status filtering, comments, and theme switching.
- Current prototype stack: TypeScript, Express, plain HTML/CSS/JavaScript, and in-memory data; Azure demo target is Linux App Service with Node.js 22 LTS.
- Validation: FlowDesk build and authorization smoke tests pass; role-specific dashboard visibility and the deployed role boundaries were verified.
- Live demo: [FlowDesk sign-in](https://flowdesk-demo-399203.azurewebsites.net/)
- Next milestone: Define DocuMind's backend stack and architecture for document ingestion and retrieval.
- DocuMind and DeployFlow: Not started.

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
