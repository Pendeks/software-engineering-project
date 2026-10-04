# FlowDesk Authentication and Authorization

## Prototype authentication model

The current prototype uses seeded demo users and role-specific bearer tokens to exercise the authorization boundaries. Credentials and tokens are static and intentionally public for this demo; this is not production authentication.

## Production direction

- User signs up with email and password.
- Passwords are hashed using a modern password hashing algorithm such as bcrypt or Argon2.
- User sessions are stored securely with expiry and invalidation support.
- API endpoints validate the session or token on every protected request.

## Identity flow

1. User registers with organization details and account metadata.
2. Credentials are validated on login.
3. Session is created and attached to an HTTP-only cookie or bearer token.
4. Protected routes require bearer/session verification.
5. Server loads the current user and organization membership context.

## Authorization model

### Roles

- Admin
- Manager
- Member
- Viewer

### Implemented access patterns

| Role | Project scope | Permissions |
|---|---|---|
| Admin | All projects | Read and manage all projects and tasks; create projects and tasks; update any task; add comments. |
| Manager | Explicitly assigned projects; newly created projects are assigned to their creator | Read scoped project/task data; create and update scoped projects and tasks; add comments. |
| Member | Explicitly assigned projects | Read scoped project/task data; create tasks assigned to themselves; update only tasks assigned to themselves; add comments. |
| Viewer | Explicitly assigned projects | Read scoped project/task data only. |

## Permission enforcement

Authorization checks occur on every protected API request; the UI only hides controls for usability and is not an enforcement boundary. Examples include:

- Only organization admins can add or remove members.
- Managers can only manage projects in their assigned scope.
- Members can only update tasks assigned to their authenticated identity.
- Out-of-scope project and task mutations return not found to avoid disclosing inaccessible resources.

The prototype stores the demo identities and their project assignments in memory. Restarting the app resets state; a database-backed membership model is required before production use.

## Auditability

The system should log privileged actions such as:

- user creation
- role changes
- project deletion
- task reassignment
- member removal

## Security considerations

- do not trust client-side role flags
- validate scoped access to every resource
- use short-lived tokens or session expiry
- rotate secrets and avoid committing credentials to source control
