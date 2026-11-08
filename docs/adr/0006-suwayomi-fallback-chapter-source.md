# 0006: Suwayomi as an optional fallback for chapters

Status: accepted, November 2026

## Context

Torrent and Usenet indexers carry manga volumes well and single chapters poorly. A chapter-first monitor mode built only on Prowlarr would often find nothing. Suwayomi-Server runs Mihon-compatible extensions (many users add the Keiyoushi extension store), has a GraphQL API, and can download chapters as CBZ.

Most of those extensions read from unofficial sites. Their availability, chapter numbering and legal standing vary, and a project that ships or recommends them draws takedown risk.

## Decision

- Prowlarr is the primary source for everything. Suwayomi is a fallback for single Chapters only, never for Volumes or Upgrades.
- A wanted Chapter goes to Suwayomi only after the Fallback delay passes without an acceptable Prowlarr release, and only for a Series with a user-confirmed Source link.
- Suwayomi is optional and off by default. The user runs it and chooses its extensions in Suwayomi itself. Tomarr never installs extensions, adds extension stores, or ships a list of sources or store URLs.
- Suwayomi downloads go through the same Import as any other download, from a shared download folder with CBZ output enabled.

## Consequences

- Chapter monitoring becomes practical for users who run Suwayomi, without making Tomarr depend on it.
- Tomarr's repository and docs stay clear of distributing scrapers or source lists.
- A second set of chapter numbers to normalize. The parser's normalization rules apply to both.
- Suwayomi's GraphQL schema changes between releases, so the adapter needs recorded fixtures per supported version and a version check on connect.
