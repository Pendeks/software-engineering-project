# FlowDesk Database Design

## Overview

The FlowDesk relational data model should support multi-tenant organization management, project coordination, task tracking, collaboration, and auditability. The design emphasizes clarity, permission boundaries, and predictable queries for a SaaS-style application.

## Core entities

### users

- id
- email
- password_hash
- full_name
- avatar_url
- created_at
- last_login_at
- is_active

### organizations

- id
- name
- slug
- created_by
- created_at

### organization_memberships

- id
- organization_id
- user_id
- role_id
- joined_at
- invited_by
- status

### roles

- id
- organization_id
- name
- description
- is_system_default

### projects

- id
- organization_id
- name
- description
- owner_user_id
- status
- created_at
- updated_at

### project_members

- id
- project_id
- user_id
- role_id
- added_by
- joined_at

### tasks

- id
- project_id
- title
- description
- status
- priority
- assignee_user_id
- reporter_user_id
- due_date
- created_at
- updated_at

### comments

- id
- task_id
- user_id
- body
- created_at

### notifications

- id
- user_id
- type
- message
- reference_id
- is_read
- created_at

### activity_log

- id
- organization_id
- user_id
- entity_type
- entity_id
- action
- metadata
- created_at

## Relationships

- One organization has many users through organization memberships.
- One organization has many projects.
- One project has many tasks and project members.
- One task has many comments and activity records.
- One user can create many tasks and comments.
- One role can apply to many memberships and project members.

## Design principles

- Keep tenant boundaries explicit with organization_id on most tables.
- Use normalized relational tables instead of storing permission state in the application layer only.
- Store audit logs separately to preserve historical actions.
- Favor strong foreign keys and constraints for integrity.

## Initial schema assumptions

- `role` values may include admin, manager, member, and viewer.
- Task statuses can begin with backlog, todo, in_progress, review, blocked, and done.
- Notifications should be lightweight and queryable for the dashboard.

## Future extensions

- add tags or labels for tasks
- add project milestones and dependencies
- add file attachments and documents
- add search indexing for comments and tasks
