# 0008: Settings stored as plain text

Status: accepted, November 2026

## Context

Settings such as API keys and credentials are stored in the database next to all other data. The encryption key would have to live next to the database, so encrypting the values only protects a database that leaks on its own, for example in a bug report or a shared backup.

## Decision

Settings are stored as plain text values in the database. The settings service is the single place in the codebase that reads and writes setting values.

## Consequences

- Anyone with read access to `/config` can read all secrets.
- As a consequence of storing secrets in plain text, structured logging must redact sensitive values before they reach the log file or stdout.
- The API must never return full secret values in responses. Later work that adds the settings page and API endpoints must enforce this.
- Encrypting the database is a future option if backups or databases start being shared, if the settings page returns stored values, or if a second user is added. Encrypting means a new dependency and a key that backups must carry.
