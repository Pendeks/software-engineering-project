# Azure Planning Notes

## Objectives

The portfolio should demonstrate engineering capability while respecting Azure student budget limits and avoiding unnecessary cloud cost.

## Planning checklist

- Check whether the service is covered by Azure for Students
- Review current pricing and region availability
- Review subscription quotas and resource limits
- Identify likely expensive resources early
- Prefer lower-cost alternatives when appropriate
- Use budgets and alerts where available
- Delete unused resources promptly
- Reassess costs during each deployment phase

## Recommended approach

Use the smallest suitable Azure footprint for each project and only deploy when the application is ready.

Typical low-cost patterns include:

- App Service for simple web applications
- Azure Database for PostgreSQL only when needed
- Azure Blob Storage for document storage and file handling
- Application Insights and Azure Monitor for observability
- Container Registry for app packaging and CI/CD
- Minimal resource sets for dev and demo scenarios

## Important note

Do not deploy production resources just because the architecture is being designed. Deployment should happen as part of each project’s deployment milestone after the application has reached the appropriate readiness level.
