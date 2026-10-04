# Repository Standards

## Goals

These standards apply across all three portfolio repositories so the work reads like a cohesive engineering portfolio.

## Repository structure

```text
project/
├── src/
├── tests/
├── docs/
│   ├── Requirements.md
│   ├── Architecture.md
│   ├── Database.md
│   ├── API.md
│   ├── Authentication.md
│   ├── Authorization.md
│   ├── Deployment.md
│   ├── Security.md
│   ├── Observability.md
│   ├── Troubleshooting.md
│   └── Lessons-Learned.md
├── screenshots/
├── Dockerfile
├── README.md
├── .gitignore
└── .github/
```

## Branching strategy

```text
main
├── feature/...
├── fix/...
├── docs/...
├── chore/...
```

## Workflow

1. Create a feature or fix branch
2. Implement the work
3. Run relevant tests and validations
4. Open a pull request
5. Review and merge after approval

## Issue conventions

Use issue labels such as:

- feature
- bug
- docs
- security
- testing
- devops
- infrastructure
- observability
- chore

Each issue should clearly define:

- objective
- scope
- acceptance criteria
- risks or dependencies

## Pull request conventions

Every meaningful pull request should explain:

- What changed
- Why it changed
- How it was tested
- Security implications
- Deployment implications

## Documentation expectations

Every project should include:

- overview
- business problem
- solution
- architecture
- stack
- database design
- API docs
- auth and authz model
- testing strategy
- deployment notes
- monitoring and observability
- security notes
- lessons learned

## Quality bar

- Prefer clear, readable code over clever code
- Keep configuration externalized and environment-aware
- Maintain security guardrails during all work
- Test the critical path before declaring work complete
- Keep logs and metrics useful and privacy-safe

## Security guardrails

Never commit:

- passwords
- API keys
- access tokens
- connection strings
- private documents
- sensitive personal data

Review screenshots and logs before sharing publicly.
