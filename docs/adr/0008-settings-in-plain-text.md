# 0008: Settings stored as plain text

Status: accepted, November 2026

## Context

Settings such as API keys and credentials are stored in the database next to all other data. Since the setting would live alongside the database, encrypting the values only protects a database that has already leaked as a whole (for example, in a bug report or a shared backup). Encrypting adds a dependency and requires a key that backups must carry and users must manage.

## Decision

Settings are stored as plain text values in the database. The settings service is the single place in the codebase that reads and writes setting values.

## Consequences

- Anyone with read access to `/config` can read all secrets. Structured logging must redact sensitive values before they reach the log file or stdout.
- The API must never return full secret values in responses (only identifiers or masked versions). Later work that adds the settings page and API endpoints must enforce this.
- Encrypting the database is a future option if backups are shared, databases are exported to logs, or multi-user access is added. At that point, a key rotation system and backup handling must come with it.
