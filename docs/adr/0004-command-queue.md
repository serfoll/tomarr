# 0004: An in-process command queue, not Celery or Redis

Status: accepted, November 2026

## Context

Tomarr runs recurring and long work: RSS sync, metadata refresh, searches, imports, translations. The work must survive restarts, respect rate limits, and show up in the UI. Users expect one container.

## Decision

Commands are rows in a `command` table. An asyncio worker pool in the app process runs them by priority. A scheduler inserts recurring Commands on intervals stored in settings. Interrupted Commands are requeued on startup. Status changes stream to the browser over Server-Sent Events. This follows the pattern Sonarr uses.

## Consequences

- No broker, no second container, nothing extra to configure.
- Commands are visible, retryable and testable as plain functions.
- Throughput is limited to one process. Fine for a single-user library manager; revisit only if real usage shows otherwise.
