# FlowDesk Architecture

## Architecture goals

FlowDesk is designed to demonstrate a realistic SaaS architecture with a clear separation between front-end, API, data layer, and security controls. The system emphasizes practicality, maintainability, and deployability without overbuilding the first version.

## High-level components

### 1. Presentation layer

- React or Next.js web application
- User authentication flows
- Project, task, and dashboard views
- Search and collaboration surfaces

### 2. Application layer

- REST API for organization, project, task, and member operations
- Business logic for authorization and validation
- Event-driven or service-oriented processing for task updates and notifications

### 3. Data layer

- PostgreSQL for relational data
- Structured schema for organizations, projects, tasks, comments, and roles
- Optional object storage for file attachments and documents

### 4. Identity and access

- Authentication provider for sign-in and session management
- Role-based access control model enforced by server-side checks
- Audit trail for privileged actions

### 5. Operations and telemetry

- Logging and structured error reporting
- API metrics and health checks
- Azure Monitor or Application Insights integration

## Core domain model

- Organization
- User
- Role
- Membership
- Project
- Task
- Comment
- Activity log

## Suggested module breakdown

- `auth`: sign-in, session, token handling, user identity
- `users`: profile and membership management
- `projects`: project lifecycle and permissions
- `tasks`: task creation, status updates, and ownership
- `collaboration`: comments, mentions, notifications, search
- `platform`: config, telemetry, health checks, deployment settings

## Security model

- Authentication required for all protected routes
- Authorization checked on every API request against the user's role and project scope; the current in-memory prototype uses seeded project assignments
- Sensitive actions limited to admins or owners
- Data validation on both client and server boundaries
- Secrets stored through environment variables or managed Azure configuration

## Deployment model

- Frontend deployed to a low-cost Azure web host
- API deployed as a containerized or App Service-backed service
- PostgreSQL hosted in a minimal managed instance for demos
- Application Insights for logs and request telemetry
- CI/CD pipeline to validate code quality and deploy approved changes

## Risks and trade-offs

- The first version should prioritize secure RBAC and core task workflows before advanced collaboration features.
- Search and notification features can be introduced iteratively after the core domain model is stable.
- Cost-conscious Azure choices should remain a first-class design decision throughout implementation.
