# Portfolio Dashboard

## Current status

- Overall status: In progress
- Current week: Week 12 of 26
- Current project: DocuMind
- Current phase: Permission-filtered retrieval and grounded answers
- Goal: answer workspace-scoped questions with relevant, traceable source citations

## Status legend

- ⚪ Backlog
- 🔵 Todo
- 🟡 In Progress
- 🟣 Review
- 🔴 Blocked
- 🟢 Done

## Project status

| Project | Status | Planned weeks |
|---|---|---|
| Portfolio Foundation | 🟢 Done | Week 1 |
| FlowDesk | 🟢 Done | Weeks 2-8 |
| DocuMind | 🟡 In Progress | Weeks 9-15 |
| DeployFlow | ⚪ Backlog | Weeks 16-21 |
| Cross-Project Observability | ⚪ Backlog | Weeks 22-24 |
| Portfolio Polish | ⚪ Backlog | Weeks 25-26 |

## Weekly progress

| Week | Focus | Status | Outcome / next step |
|---|---|---|---|
| 1 | Portfolio setup | 🟢 Done | Workspace structure and repository standards established. |
| 2 | FlowDesk planning and design | 🟢 Done | Requirements, architecture, database, API, authentication, and security planning docs created. |
| 3 | Authentication | 🟢 Done | Demo login, token handling, and protected API routes implemented. |
| 4 | Authorization and RBAC | 🟢 Done | Added server-enforced Admin/Manager/Member/Viewer rules and project-scoped reads/mutations; regression tests cover role boundaries. |
| 5 | Projects and tasks | 🟢 Done | Project and task create/update workflows implemented. |
| 6 | Collaboration and search | 🟢 Done | Task comments, task search, and status filtering implemented. |
| 7 | Frontend and testing | 🟢 Done | Login/dashboard, theme switching, responsive layout, status colors, and browser validation are complete; smoke tests pass. |
| 8 | Deployment and observability | 🟢 Done | Temporary Linux F1 demo deployed in Indonesia Central. Reviewed 60 application requests with no logged errors, verified health/readiness, and deployed Admin/Manager/Member/Viewer authorization. The demo remains online for temporary use; delete its resource group when finished. |
| 9 | DocuMind AI architecture and pipelines | 🟢 Done | Selected Python/FastAPI, PostgreSQL/pgvector, private Azure Blob Storage, and Azure OpenAI behind provider interfaces; documented pipeline and access boundaries. |
| 10 | DocuMind document management and storage | 🟢 Done | Added workspace-scoped document APIs, private local storage, metadata, upload validation, retryable deletion, and PDF/DOCX plus isolation/failure tests. |
| 11 | DocuMind processing and embeddings | 🟣 Review | Added PDF/DOCX/text extraction, source-offset chunking, a queued/retryable worker, Azure OpenAI embeddings, pgvector persistence, stale-job recovery, and 17 processing tests. Live Azure/PostgreSQL validation remains pending credentials and infrastructure. |
| 12 | DocuMind RAG MVP | 🟡 In Progress | Added authorized workspace-filtered cosine retrieval, an Azure OpenAI chat adapter, citation validation, abstention behavior, and question API tests. |
| 13 | DocuMind security and quality | ⚪ Backlog | Add security controls and quality checks. |
| 14 | DocuMind user experience and UI | ⚪ Backlog | Build and validate the user-facing experience. |
| 15 | DocuMind deployment and monitoring | ⚪ Backlog | Deploy the application and add monitoring. |
| 16 | DeployFlow CI workflow | ⚪ Backlog | Establish continuous integration. |
| 17 | DeployFlow Docker and registry | ⚪ Backlog | Containerize the app and configure an image registry. |
| 18 | DeployFlow infrastructure as code | ⚪ Backlog | Provision cloud resources as code. |
| 19 | DeployFlow CD workflow | ⚪ Backlog | Automate continuous deployment. |
| 20 | DeployFlow reliability and rollback | ⚪ Backlog | Add release safety and rollback practices. |
| 21 | DeployFlow security and polish | ⚪ Backlog | Harden and document the delivery platform. |
| 22 | FlowDesk monitoring | ⚪ Backlog | Add deeper FlowDesk monitoring. |
| 23 | DocuMind monitoring | ⚪ Backlog | Add DocuMind monitoring. |
| 24 | DeployFlow observability and incident simulation | ⚪ Backlog | Validate operational response across the delivery platform. |
| 25 | Documentation and evidence | ⚪ Backlog | Collect project documentation and portfolio evidence. |
| 26 | Final review | ⚪ Backlog | Review completeness and prepare the portfolio for presentation. |

## Immediate next tasks

1. Evaluate retrieval thresholds and verify ingestion and question answering against configured Azure OpenAI and PostgreSQL deployments.
2. Delete the FlowDesk demo resource group when the temporary demo is no longer needed.
