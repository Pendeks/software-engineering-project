# FlowDesk Observability and Monitoring

## Goal

FlowDesk should demonstrate operational awareness through logs, metrics, and health checks. Even in a demo-friendly portfolio, tracing and observability signal maturity and production readiness.

## Core signals

- API request latency
- authentication failures
- task update volume
- permission-denied errors
- database query failures
- deployment health status

## Recommended instrumentation

- structured request logging
- correlation IDs for user actions
- health endpoint for service readiness
- error tracking for failed requests
- application telemetry exported to Azure Monitor or Application Insights

## Useful dashboards

- active users by organization
- project creation throughput
- task status distribution
- failed authentication attempts
- high-latency API routes

## Operational expectations

- review failed requests during demos and release checkpoints
- keep logs concise and privacy-safe
- make health and diagnostics easy to understand for recruiters and reviewers
- document known issues and recovery steps in the project notes
