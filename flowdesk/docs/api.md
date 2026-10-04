# FlowDesk API Design

## Overview

The FlowDesk API should expose a clear, consistent interface for organization, project, task, and collaboration workflows. The API should be designed for authorization-aware access, strong validation, and predictable error responses.

## Base conventions

- Base path: `/api/v1`
- JSON request and response payloads
- Standard HTTP status codes
- Consistent error body structure
- Authorization via session or bearer token

## Authentication endpoints

### POST /api/v1/auth/register

Creates a new user account and organization.

### POST /api/v1/auth/login

Authenticates a user and returns a session token or cookie.

### POST /api/v1/auth/logout

Invalidates the active session.

### GET /api/v1/auth/me

Returns the current authenticated user profile.

## Organization endpoints

### GET /api/v1/organizations
### GET /api/v1/organizations/:id
### POST /api/v1/organizations
### PATCH /api/v1/organizations/:id

## Membership endpoints

### GET /api/v1/organizations/:id/members
### POST /api/v1/organizations/:id/members
### PATCH /api/v1/organizations/:id/members/:memberId
### DELETE /api/v1/organizations/:id/members/:memberId

## Project endpoints

### GET /api/v1/projects
### GET /api/v1/projects/:id
### POST /api/v1/projects
### PATCH /api/v1/projects/:id
### DELETE /api/v1/projects/:id

## Task endpoints

### GET /api/v1/projects/:projectId/tasks
### GET /api/v1/tasks/:id
### POST /api/v1/projects/:projectId/tasks
### PATCH /api/v1/tasks/:id
### DELETE /api/v1/tasks/:id

## Comment endpoints

### GET /api/v1/tasks/:taskId/comments
### POST /api/v1/tasks/:taskId/comments

## Search endpoints

### GET /api/v1/search?q=...

Returns matched tasks, projects, and comments relevant to the authenticated user.

## Error model

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "You do not have permission to update this task.",
    "details": ["project_member"],
    "request_id": "abc123"
  }
}
```

## Authorization rules

- Admins can read and manage all projects and tasks.
- Managers can read and manage projects and tasks in their assigned project scope.
- Members can read assigned projects, create tasks assigned to themselves, and update only their own tasks.
- Viewers can read assigned projects and tasks but cannot create, edit, or comment.
- Out-of-scope project and task mutations return not found; authenticated but disallowed actions return forbidden.

## Validation expectations

- Reject invalid email format and password length rules.
- Require required project and task fields.
- Enforce ownership checks before mutation.
- Use server-side validation even when frontend validation exists.
