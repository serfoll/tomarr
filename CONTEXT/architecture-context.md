# Architecture context

Where code lives and how data moves through Tomarr. Stack choices are in `CLAUDE.md` and `docs/adr/0001`. Vocabulary is in `CONTEXT/CONTEXT.md`.

## Shape

One Docker container runs one Python process. FastAPI serves the REST API under `/api/v1`, the Server-Sent Events stream, and the built frontend as static files. Background work runs in the same process through the command queue. State lives in one SQLite database in `/config`.

```
browser ──> FastAPI ──> services ──> SQLite
                │           │
                │           └─> command queue ──> providers / Prowlarr / download clients / Kavita / Gemini
                └─> SSE (queue and activity updates)
```

## Repo layout

```
backend/
  src/tomarr/
    api/              routes and request/response schemas, one module per resource
    core/             config, database session, auth, logging, rate limiting, HTTP client factory
    domain/           SQLAlchemy models and enums (Series, Edition, Volume, Chapter, Mapping, ...)
    services/         business logic called by routes and commands
    commands/         command queue, scheduler, one module per command type
    parser/           release-name parser (pure functions, no I/O)
    providers/        metadata providers, one package each, behind providers/base.py
    indexers/         Prowlarr, Torznab, Newznab
    download_clients/ qBittorrent, SABnzbd
    chapter_sources/  Suwayomi (GraphQL)
    library_servers/  Kavita
    llm/              provider interface, Gemini implementation, prompts, glossary building
    importer/         file handling: archives, CBZ, ComicInfo.xml, renaming, linking
  migrations/         Alembic
  tests/              mirrors src/tomarr; fixtures and cassettes in tests/fixtures
frontend/
  src/
    routes/           TanStack Router file routes
    components/       shared UI, one per file
    api/              generated client and query hooks
docker/               Dockerfile, entrypoint, docker-compose.dev.yml
docs/adr/             architecture decision records
CONTEXT/              product, process and (later) design docs
```

## Layer rules

- `api/` validates input, calls a service, returns a schema. No database queries and no business rules in routes.
- `services/` holds the rules and owns transactions. Services call providers and clients through their interfaces, never through a concrete class.
- `parser/` and the matching and scoring code are pure: no database, no network, no clock. That's what makes them testable against a large corpus.
- `providers/`, `indexers/`, `download_clients/`, `chapter_sources/`, `library_servers/` and `llm/` are adapters. They translate an external API into Tomarr's types and nothing else.
- Commands are thin: load what they need, call a service, record the outcome.

## Data flow

**Adding a series.** The API calls `SeriesService.resolve(query)`, which searches MangaBaka and AniList, scores candidates with rapidfuzz against titles and aliases, and returns suggestions. On add, the service stores the Series with its External IDs and Aliases and queues `RefreshSeriesMetadata`.

**Refreshing metadata.** `RefreshSeriesMetadata` asks each linked Provider for its part:

| Provider | Gives |
|---|---|
| MangaBaka | External IDs across Providers, totals, status |
| AniList | Titles in all scripts, format, cover |
| MangaDex | Volume to chapter aggregate (Mapping, provenance `mangadex_aggregate`) |
| MangaUpdates | Latest released chapters |
| Rakuten Books | Japanese volumes: ISBN, date, synopsis, upcoming volumes |
| NDL | Authoritative list of published Japanese volumes and ISBNs |
| openBD | Enrichment by ISBN, including publisher descriptions |
| WEBTOON RSS | Latest episodes for webtoon Series |

Results are merged by Provenance priority. Locked fields and Mappings are skipped. New Japanese synopses queue `TranslateSynopses` when a Gemini key is set.

**Searching.** `SearchWanted` builds queries from the Series title and Aliases and calls Prowlarr, using only indexers with the configured Indexer tag and each indexer's configured Categories. Every Release name goes through the parser, then a Decision is made per Parsed release against the quality profile and the Series' Wanted items. The best accepted release is grabbed if its Confidence meets the threshold; otherwise it goes to Pending review. `RssSync` does the same for recent releases on a schedule. Interactive search returns every Release with its Parsed release, Decision and Confidence, and lets the user grab or override any of them.

**Chapter source fallback.** `FallbackToChapterSource` runs on a schedule. For each wanted Chapter older than the Fallback delay with no grab in progress, on a Series with a Source link, it asks Suwayomi to download that chapter. Volumes and upgrades never come from Suwayomi. If the Source link's chapter list doesn't contain the Chapter number, nothing is queued and the Chapter stays wanted.

**Linking a Series to Suwayomi.** `ChapterSourceService.find_links(series)` searches the user's installed Suwayomi sources with the Series title and Aliases, scores candidates with the same matcher, and returns suggestions. The user confirms one, which becomes the Source link. Tomarr never installs extensions or adds extension stores; that's done in Suwayomi.

**Importing.** `CheckDownloads` polls the download clients and the Suwayomi download queue. Finished items queue `ImportDownload`, which extracts the archive, converts to CBZ, writes `ComicInfo.xml`, hardlinks (or copies) into the Series folder under the root folder, records the files, and calls Kavita to scan that folder.

## Suwayomi adapter

Suwayomi-Server exposes a GraphQL API at `/api/graphql`. The adapter in `chapter_sources/suwayomi/` covers: listing installed sources, searching a source, reading a manga's chapter list, enqueueing chapter downloads and reading download status. Confirm every query and mutation against the running server's schema before writing it; the API changes between Suwayomi releases.

Downloads are imported from Suwayomi's download folder, mounted into Tomarr's container. Tomarr expects Suwayomi's "download as CBZ" option on and reads chapters from there, then runs the normal Import (rename, `ComicInfo.xml`, link into the Series folder, Kavita scan). Chapter numbers reported by Suwayomi are normalized with the same rules the parser uses for release names.

## Command queue

Commands are rows in a `command` table with a type, JSON payload, status, timestamps and result. A small asyncio worker pool takes queued commands in priority order. A scheduler inserts recurring commands (RSS sync, download checks, metadata refresh) on intervals stored in settings. Commands interrupted by a restart go back to queued on startup. Status changes are pushed to the browser over SSE. Why this and not Celery: `docs/adr/0004`.

## Rate limits and caching

Every outbound HTTP client comes from `HttpClientFactory` in `core/http.py`. The app builds one factory at startup and keeps it on `app.state.http`. A ruff rule (`TID251`) fails any other module that creates an `httpx2.AsyncClient`, tests included.

An adapter declares an `HttpPolicy`: the service name a person sees ("Prowlarr"), how many requests may start in an interval, and a cache TTL in seconds. It then calls `factory.client(policy, base_url=..., auth=..., headers=...)`. Limits and cache lifetimes belong to the adapter, never to callers. Clients with the same policy name share one rate limiter (`core/rate_limit.py`, a sliding window), so the limit holds across every client of that service.

Each request goes through the same steps: cache lookup, rate limiter, network, 429 check, cache write. A cache hit returns before the limiter, so it uses none of the quota.

The cache (`core/response_cache.py`, table `http_cache`) stores only `GET` responses with status 200, and only when the policy sets a TTL above 0. `Cache-Control` is ignored. POST requests, other status codes and policies without a TTL are never cached. The key is a SHA-256 of the policy name, the method and the full URL, query included. The URL itself is never stored, because some services put an API key in the query string. The stored body is the raw one, still content-encoded, so a replayed response decodes the same way a live one does. Expired rows stay until the same key is fetched again.

Credentials go through `auth=` or headers. The factory refuses a `base_url` with a username or password in it. Any URL that goes into a log line or an error passes through `safe_url()` first, which drops them. Calls are logged by policy name only, never by URL.

When a service answers 429, the transport raises `RateLimited` with the policy name and the `Retry-After` delay in seconds (`None` when the header is missing or unreadable), logs one warning with the name and the delay, and caches nothing. Through the API it surfaces as 503 `rate_limited` ("Prowlarr is rate limiting Tomarr. Try again later."). Backing off and retrying is the command queue's job (#11). A command must never spin on a 429.

## LLM

`llm/base.py` defines the interface (`translate`, `extract_chapter_ranges`, `disambiguate_titles`, `parse_release_name`). `llm/gemini.py` implements it with `google-genai`, using structured output with Pydantic models as the response schema.

Rules:

- Deterministic code runs first. The LLM is called only when regex parsing or fuzzy matching fails or is ambiguous.
- Calls are batched (several synopses per request), cached by a hash of the input, and run only inside Commands so they respect the queue's backoff.
- Translation prompts include a glossary built from AniList character and title names, so names stay consistent across volumes.
- Output is validated against the schema. Invalid output is logged by Command ID and discarded, never stored.
- With no key set, every LLM feature is off and the app works without it.
- The settings page states that on Gemini's free tier, Google may use submitted content to improve its products.

See `docs/adr/0005`.

## Configuration and storage

`/config` holds `tomarr.db`, `config.toml`, `logs/` and `backups/`. The database is SQLite with WAL (write-ahead logging) and foreign keys enabled for every connection. Migrations are applied on startup from `src/tomarr/migrations/` before the app accepts requests. `config.toml` holds only what's needed before the database opens: bind address, port, URL base, API key, log level. It has three sections: `[server]` with `bindaddress`, `port` and `urlbase`, `[auth]` with `apikey`, and `[log]` with `level`. Everything else is a setting in the database, edited in the UI. Settings are read and written through `SettingsService`, and all setting keys are declared through its registry. Secrets are stored as plain text values. See `docs/adr/0008`. Environment variables override `config.toml` (`TOMARR__SERVER__PORT` style), written `TOMARR__SECTION__KEY`, so the log level is `TOMARR__LOG__LEVEL`. The log file is `/config/logs/tomarr.log`. The container runs as PUID/PGID from the environment.

## Auth

Every API request needs either the `X-Api-Key` header or a session cookie from the form login. An option allows unauthenticated access from local addresses, off by default. The API key is accepted in the header only. First-run credentials are set through `POST /api/v1/auth/setup`. Settings `auth.credentials` and `auth.local_bypass` control credentials and local bypass. `GET /api/v1/system/health` is the one open system route. The local bypass judges only the connecting address, so behind a reverse proxy that adds no forwarding headers every request looks local, and the option should stay off. The session cookie is marked `Secure` only when the request reaches Tomarr over HTTPS, so behind a proxy that terminates TLS the server must trust the proxy headers for the flag to apply (#14 sets this up).

## Error handling and logging

Structured logs to stdout and a rotating file in `/config/logs`. A shared redaction filter strips API keys and query strings before anything is written. Log lines written while a request is handled carry its `request_id`. No external error reporting in MVP.

Every API error has the JSON body `{"code": ..., "message": ..., "request_id": ...}`. `code` is an `ErrorCode` value from `tomarr.core.errors`, such as `validation_failed` or `internal_error`. `message` is fixed text per code and never includes request details. `request_id` is the ID on that request's log lines, so the details of an error are in the log under it.

Every response, errors included, has an `X-Request-ID` header. An inbound `X-Request-ID` is reused only when it matches `[A-Za-z0-9._-]{1,64}`. Any other value is replaced with a generated ID, not cleaned up.
