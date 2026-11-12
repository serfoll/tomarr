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
    api/              client generated from the backend's OpenAPI schema (`pnpm gen:api`), and the query hooks that call it
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

Commands are rows in the `command` table: type, JSON payload, status (`queued`, `running`, `completed`, `failed`), priority, `queued_at`, `started_at`, `ended_at`, `not_before`, result and `waiting_on`. Times are epoch seconds. `CommandService` (`services/commands.py`) makes every change to a row, each in its own short transaction, and calls an `on_change` listener after the commit, never inside it.

The lifespan builds the service, an in-process `Broadcaster` (`core/broadcaster.py`), a `CommandRegistry` that maps each type to its handler, the `CommandRunner` and the `CommandScheduler`, and keeps them on `app.state`. `on_change` publishes the Command to the broadcaster and wakes the runner.

- **Runner** (`commands/runner.py`). Two asyncio workers. Each claims the next due Command (highest priority, then oldest) with one `UPDATE ... RETURNING`, so two workers never take the same row. When nothing is due a worker waits until it is woken, until the earliest `not_before`, or 30 seconds at most. No transaction stays open while a handler runs.
- **Failure.** The runner and the scheduler loop are the boundaries that catch broad exceptions, and the service also contains a failing `on_change` listener. A failed Command stores only `{"error": "<ErrorCode>"}`: the code of a `DomainError`, or `internal_error` for anything else, including a handler that cancels itself. If storing a Command's outcome fails, the worker makes one more attempt to fail it as `internal_error`, so no Command stays `running` by mistake. A Command that hits `RateLimited` goes back to `queued` with `not_before` set from `Retry-After` (60 seconds without one or with a non-number, kept between 5 seconds and an hour) and `waiting_on` set to the service name. The scheduler loop logs a failed tick and keeps going.
- **Restarts.** At startup, before the workers start, every `running` row goes back to `queued`. Shutdown cancels only running handlers and leaves their rows `running`, so the next start runs them again. It never cancels a database call: each worker and the scheduler finish the call they are in and then exit. Handlers must be repeatable. Starting the runner or the scheduler while it is running raises.
- **Scheduler** (`commands/scheduler.py`). Every 10 seconds it queues each scheduled type whose interval has passed since it was last queued and that has no queued or running row. Intervals are settings in seconds, and `0` turns one off. The only scheduled type so far is `PurgeHttpCache`, which deletes expired `http_cache` rows. It runs daily by default (`schedule.purge_http_cache`), and the first start queues it right away.
- **Events.** `GET /api/v1/commands/events` needs auth and is a Server-Sent Events stream. It sends a `snapshot` of every queued and running Command, then a `command` event for each change. An event is a `CommandStatusEvent`: the Command's state without its payload or result. A client that falls 100 events behind is dropped. Shutdown closes the broadcaster first, which ends every open stream, then stops the scheduler and the runner.

Nothing deletes finished rows yet, so recurring Commands add rows for good. A retention rule is a follow-up. Why this and not Celery: `docs/adr/0004`.

## Rate limits and caching

Every outbound HTTP client comes from `HttpClientFactory` in `core/http.py`. The app builds one factory at startup and keeps it on `app.state.http`. A ruff rule (`TID251`) fails any other module that uses `httpx2.AsyncClient`, `httpx2.Client` or the module-level helpers (`httpx2.get`, `httpx2.request`, `httpx2.stream` and the rest), tests included.

An adapter declares an `HttpPolicy`: the service name a person sees ("Prowlarr"), how many requests may start in an interval, and a cache TTL in seconds. It then calls `factory.client(policy, base_url=..., auth=..., headers=...)`. Limits and cache lifetimes belong to the adapter, never to callers. Clients with the same policy name share one rate limiter (`core/rate_limit.py`, a sliding window), so the limit holds across every client of that service. A policy whose name is already in use with a different `requests` or `interval` is refused with a `ValueError`.

Each request goes through the same steps: userinfo check, cache lookup, rate limiter, network, 429 check, cache write. A cache hit returns before the limiter, so it uses none of the quota.

The cache (`core/response_cache.py`, table `http_cache`) stores only `GET` responses with status 200, and only when the policy sets a TTL above 0. `Cache-Control` is ignored. POST requests, other status codes and policies without a TTL are never cached. The key is a SHA-256 of the policy name, the method and the full URL, query included. The URL itself is never stored, because some services put an API key in the query string. The stored body is the raw one, still content-encoded, and the headers keep their raw bytes, so a replayed response decodes the same way a live one does. The next 200 for the same key overwrites the row, and the daily `PurgeHttpCache` Command deletes expired rows.

Credentials go through `auth=` or headers. The factory refuses a `base_url` with a username or password in it, and the transport refuses any request URL that still carries one, before the cache or the network sees it. The factory logs the policy name only, never a URL, and keeps the `httpx2` and `httpcore2` loggers at WARNING because below that they write URLs, hosts and response headers. `safe_url()` drops the username and password from a URL; adapters call it whenever they put a URL in a log line or an error.

When a service answers 429, the transport raises `RateLimited` with the policy name and the `Retry-After` delay in seconds (`None` when the header is missing or unreadable), logs one warning with the name and the delay, and caches nothing. Through the API it surfaces as 503 `rate_limited` ("Prowlarr is rate limiting Tomarr. Try again later."). When a Command's handler raises it, the runner puts the Command back in the queue until the delay has passed (see Command queue). A Command must never spin on a 429.

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

`/config` holds `tomarr.db`, `config.toml`, `logs/` and `backups/`. The database is SQLite with WAL (write-ahead logging) and foreign keys enabled for every connection. Migrations are applied on startup from `src/tomarr/migrations/` before the app accepts requests. `config.toml` holds only what's needed before the database opens: bind address, port, URL base, API key, log level. It has three sections: `[server]` with `bindaddress`, `port` and `urlbase`, `[auth]` with `apikey`, and `[log]` with `level`. Everything else is a setting in the database, edited in the UI. Settings are read and written through `SettingsService`, and all setting keys are declared through its registry. Secrets are stored as plain text values. See `docs/adr/0008`. Environment variables override `config.toml` (`TOMARR__SERVER__PORT` style), written `TOMARR__SECTION__KEY`, so the log level is `TOMARR__LOG__LEVEL`. The log file is `/config/logs/tomarr.log`. The container runs as PUID/PGID from the environment. Two internal variables exist for tests and local runs and are not user settings: `TOMARR_CONFIG_DIR` moves `/config`, and `TOMARR_STATIC_DIR` sets where the frontend build is read from. An empty value of either counts as unset.

## Serving the frontend

`api/static.py` registers a catch-all route at `/{path:path}` for `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE` and `OPTIONS`, as the last route in `create_app()`, so every API route, `/docs`, `/redoc` and `/openapi.json` match first. It is left out of the OpenAPI schema. The build is read from `TOMARR_STATIC_DIR`, which defaults to `frontend/dist` in the checkout. If the directory has no `index.html` (missing, or a half-written build), the route is not registered and the backend behaves as it does without a frontend.

- The catch-all never matches a path under `/api`. Routing there works as if there were no build: a wrong method on a real API route is a 405 with that route's `Allow` header, and a path that matches no API route is the JSON 404 for any method. Neither ever returns `index.html`.
- A path that resolves to a file inside the build directory returns that file for `GET` and `HEAD`. A path that resolves outside it, by `..`, an absolute path or a symlink, or that is too long for the file system, is treated as any other unknown path.
- An unknown path under `/assets` is the JSON 404, so a browser holding an old `index.html` never gets HTML for a module script.
- Any other path returns `index.html` with status 200 for `GET` and `HEAD`, so a deep link to a client route loads the app and the router takes over.
- Outside `/api`, the other registered methods get the JSON 405 with `Allow: GET, HEAD`.
- The build is made for the base path `/`. `urlbase` is not applied to it yet.

In development, `pnpm dev` runs the Vite dev server, which proxies `/api` to the backend on `127.0.0.1:8000`. If `TOMARR_DEV_API_KEY` is set, the proxy adds it as the `X-Api-Key` header, so the shell can call guarded routes without signing in. The variable is read by `vite.config.ts` only and never ships in the build.

The frontend's API types are generated from the backend's OpenAPI schema into `frontend/src/api/schema.gen.ts`. `pnpm gen:api` regenerates them after a backend schema change. `pnpm gen:api:check` fails when the committed file is out of date and is meant to run in CI (issue #16 wires it in). Only `src/api/client.ts` makes requests, and the query hooks in `src/api/` call it.

## Auth

Every API request needs either the `X-Api-Key` header or a session cookie from the form login. An option allows unauthenticated access from local addresses, off by default. The API key is accepted in the header only. First-run credentials are set through `POST /api/v1/auth/setup`. Settings `auth.credentials` and `auth.local_bypass` control credentials and local bypass. `GET /api/v1/system/health` is the one open system route. The local bypass judges only the connecting address, so behind a reverse proxy that adds no forwarding headers every request looks local, and the option should stay off. The session cookie is marked `Secure` only when the request reaches Tomarr over HTTPS, so behind a proxy that terminates TLS the server must trust the proxy headers for the flag to apply (#14 sets this up).

`GET /api/v1/auth/status` is open and returns `setup_required`, `authenticated` and `password_min_length`, the minimum the setup form enforces, so the sign-up page shows the server's number.

In the frontend, the app routes sit under the pathless layout `src/routes/_authed.tsx`. Its `beforeLoad` reads the auth status from the `QueryClient` in the router context and sends the visitor to `/sign-up` on a fresh install, or to `/sign-in?redirect=<requested path>` when not signed in. `/sign-up` and `/sign-in` run the reverse check. The guard trusts the cached status until a sign-up, sign-in or sign-out refetches it, and fetches it again if the last refetch failed. `/sign-up` posts to `/api/v1/auth/setup` and lands in the app; a 409 sends the visitor to sign-in. `/sign-in` posts to `/api/v1/auth/login` and follows the `redirect` param only when `safeRedirectPath` accepts it as a same-origin path, otherwise `/`. The "Sign out" button in the layout posts to `/api/v1/auth/logout`. The layout watches the cached status, and once it turns unauthenticated it drops every other cached query and reruns the guards, which land the visitor on `/sign-in`. A 401 on any query other than the status takes the same path, so a session that ends while the page is open sends the visitor to sign-in with the page they were on. A visitor let in by the API key or the local bypass stays authenticated after signing out, because the cookie was not what let them in.

## Error handling and logging

Structured logs to stdout and a rotating file in `/config/logs`. A shared redaction filter strips API keys and query strings before anything is written. Log lines written while a request is handled carry its `request_id`. No external error reporting in MVP.

Every API error has the JSON body `{"code": ..., "message": ..., "request_id": ...}`. `code` is an `ErrorCode` value from `tomarr.core.errors`, such as `validation_failed` or `internal_error`. `message` is fixed text per code and never includes request details. `request_id` is the ID on that request's log lines, so the details of an error are in the log under it.

Every response, errors included, has an `X-Request-ID` header. An inbound `X-Request-ID` is reused only when it matches `[A-Za-z0-9._-]{1,64}`. Any other value is replaced with a generated ID, not cleaned up.
