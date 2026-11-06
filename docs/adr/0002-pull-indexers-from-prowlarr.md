# 0002: Pull indexers from Prowlarr instead of native app sync

Status: accepted, November 2026

## Context

Prowlarr pushes indexers into Sonarr, Radarr, Lidarr and others through per-app code inside Prowlarr (Settings, Apps). An app only appears there if Prowlarr ships support for it, which would mean a pull request to Prowlarr.

## Decision

The user enters Prowlarr's URL and API key in Tomarr. Tomarr reads the indexer list from Prowlarr's API and searches through Prowlarr. Direct Torznab and Newznab indexers are also supported for users without Prowlarr.

## Consequences

- Works with any Prowlarr version, with no upstream dependency.
- Indexer categories and capabilities come from Prowlarr, so Tomarr doesn't keep its own indexer definitions.
- Native app sync can be proposed upstream later, once Tomarr has users. Nothing here blocks it.
