# Tomarr

Tomarr is a self-hosted *arr for manga, manhwa and webtoons. It tracks series down to volumes and chapters, finds releases through Prowlarr (with Suwayomi as an optional fallback for single chapters), sends them to a download client, imports them with clean metadata and tells Kavita to rescan.

Project Board: https://github.com/users/serfoll/projects/16

## Read first

| File | Read when |
|---|---|
| `CONTEXT/PRODUCT.md` | Deciding what to build or whether something is in scope |
| `CONTEXT/CONTEXT.md` | Naming anything. Use the glossary terms exactly |
| `CONTEXT/architecture-context.md` | Deciding where code lives and how data flows |
| `CONTEXT/code-standards.md` | Writing or reviewing code and tests |
| `CONTEXT/ai-workflow-rules.md` | Always. How an agent works in this repo |
| `CONTEXT/copy.md` | Writing anything a person reads |
| `docs/adr/` | Before changing a decision recorded there |

## Stack notes

- Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.1 (typed) with Alembic, SQLite in WAL mode, httpx2 (async). Package manager: uv. Lint and format: ruff. Types: pyright. Tests: pytest with recorded HTTP fixtures.
- Frontend: React and TypeScript in a Vite SPA, TanStack Router, Query and Table. API client generated from the backend's OpenAPI schema. Package manager: pnpm. Lint and format: Biome. Tests: Vitest.
- LLM: Google Gemini through the official `google-genai` SDK, bring your own key, behind a provider interface.
- Shipping: one Docker image (multi-arch amd64 and arm64) published to GHCR. Config and database live in `/config`.
- License: AGPL-3.0.

Design (colors, type, components) is not decided yet. Don't invent a design system; use unstyled headless primitives until `CONTEXT/design/` exists.

## Approved dependencies

Signed off 2026-11-08. Versions are the current stable releases on that date. The lockfile (`uv.lock`, `pnpm-lock.yaml`) is what is installed. "Dev" rows are dev dependencies. "Added by audit" rows were not in the original proposal and can be struck.

### Backend

| Package | Version | Reason |
|---|---|---|
| `fastapi` | 0.162.2 | API, OpenAPI schema and built-in SSE (ADR 0001, #11). Plain, not `[standard]` |
| `uvicorn[standard]` | 0.54.0 | ASGI server. `standard` adds uvloop, httptools and watchfiles for `--reload` (uvicorn README) |
| `pydantic` | 2.14.3 | API schemas, settings, Gemini response schemas (ADR 0001, ADR 0005) |
| `pydantic-settings` | 2.16.2 | Reads `config.toml` and `TOMARR__SECTION__KEY` overrides (#6) |
| `sqlalchemy[asyncio]` | 2.1.8 | ORM (ADR 0001, #7). 2.1 no longer installs greenlet by default, so the extra is needed. Alembic 1.20.1 requires SQLAlchemy 2.0 or later and its changelog names 2.1 fixes |
| `alembic` | 1.20.1 | Migrations (#7) |
| `aiosqlite` | 0.22.1 | SQLite driver for the async engine (#7). Signed off 2026-11-09 |
| `httpx2` | 2.16.0 | Outbound HTTP through `core/http.py` (#10). Replaces `httpx`, last released 2024-12-06. `google-genai` 3.0.0 already requires it |
| `rapidfuzz` | 3.14.6 | Title matching (ADR 0001, #20) |
| `lxml` | 6.1.3 | Torznab, Newznab, WEBTOON RSS and `ComicInfo.xml`, with schema validation (#29, #36, #45) |
| `google-genai` | 3.0.0 | Gemini adapter (ADR 0005, #32) |
| `python-multipart` | 0.0.33 | FastAPI `Form` needs it for the login form (#8). Added by audit |
| `pwdlib[argon2]` | 0.3.1 | Password hash for the first-run login (#8). FastAPI's docs recommend it with Argon2. Added by audit |
| `itsdangerous` | 2.2.0 | Signs the session cookie (#8). Signed off 2026-11-09 |
| `tomli-w` | 1.2.0 | Writes the default `config.toml` on first run, since `tomllib` only reads (#6). Added by audit |
| `ruff` | 0.17.4 | Dev. Lint and format (#5) |
| `pyright` | 1.1.414 | Dev. Strict types on `src/tomarr` (#5) |
| `pytest` | 9.2.0 | Dev. Test runner (#5) |
| `pytest-asyncio` | 1.4.1.post1 | Dev. Async tests (#5) |
| `pytest-recording` | 0.14.1 | Dev. Cassettes and `--block-network` (#5) |
| `pyyaml` | 6.0.3 | Dev. Loads the golden corpus in `tests/fixtures/releases/*.yaml` (#19). Added by audit |
| `types-lxml` | 2026.2.16 | Dev. lxml ships no types and pyright runs strict. Added by audit |

`httpx2` records and replays with `vcrpy` 9.4.2 and `pytest-recording` 0.14.1, checked 2026-11-08.

### Frontend

| Package | Version | Reason |
|---|---|---|
| `react`, `react-dom` | 19.3.1 | UI (ADR 0001, #12) |
| `vite` | 8.3.6 | Build and dev server (#12) |
| `typescript` | 5.9.3 | Held at 5.x: `openapi-typescript` 7.13.0 peers `^5.x` and 5.9.3 is the newest 5.x. Revisit when it widens its range |
| `@tanstack/react-router` | 1.170.46 | File routes (#12) |
| `@tanstack/react-query` | 5.107.1 | Server state (#12) |
| `@tanstack/react-table` | 9.3.1 | Data tables (Stack notes) |
| `@tanstack/react-virtual` | 3.14.26 | Virtualized Library list (#54) |
| `openapi-typescript` | 7.13.0 | Generates API types from the OpenAPI schema (#13) |
| `openapi-fetch` | 0.17.0 | Typed client over the generated types (#13) |
| `@tanstack/router-plugin` | 1.169.0 | Vite plugin for file routes (#12). Added by audit |
| `@vitejs/plugin-react` | 6.2.1 | Vite React plugin (#12). Added by audit |
| `@types/react`, `@types/react-dom` | 19.3.0 | React types. Added by audit |
| `@types/node` | 26.6.6 | Node types for `vite.config.ts`. Match the build stage's Node major. Added by audit |
| `@biomejs/biome` | 2.6.6 | Dev. Lint and format (#12) |
| `vitest` | 5.1.0 | Dev. Test runner (#12) |
| `jsdom` | 31.0.0 | Dev. DOM for component tests. Added by audit |
| `@testing-library/react` | 16.3.3 | Dev. Component tests. Added by audit |
| `@testing-library/dom` | 10.4.2 | Dev. Peer of `@testing-library/react`. Added by audit |

Vitest 5.1 and jsdom 31 set the Node floor for the Dockerfile's Node stage: 22.22.2 or later in 22, 24.15 or later in 24, or 26 and up.

### System

| Package | Version | Reason |
|---|---|---|
| `7zip` | 25.01+dfsg-1~deb13u2 | Extracts zip and RAR for Import (#14, #45). Debian main |
| `7zip-rar` | 25.00+ds-1+deb13u1 | Lets `7z` read CBR and RAR5. Debian puts it in `non-free` because of the unRAR licence, so the image must enable that apt component |

Base image: `python:3.13-slim` (3.13.18, Debian 13 trixie).

Deferred by the user until the work needs them: `pillow` (image conversion). It is asked for sign-off when that work starts.

Scaffold issues install only packages listed here. Any later addition is asked first, then added to this list in the same PR.

## Commands

The backend and frontend are scaffolded; the Docker parts are not yet. Backend commands run from `backend/` and frontend commands from `frontend/`. Until a command exists in `pyproject.toml`, `package.json` or a compose file, don't reference it as if it does.

| Task | Command |
|---|---|
| Backend tests (from `backend/`) | `uv run pytest` |
| Backend lint and types (from `backend/`) | `uv run ruff check . && uv run ruff format --check . && uv run pyright` |
| Backend dev server (from `backend/`). The timeout stops an open event stream from blocking Ctrl-C | `uv run uvicorn tomarr.app:create_app --factory --reload --timeout-graceful-shutdown 5` |
| Frontend dev server (from `frontend/`). Proxies `/api` to the backend on `127.0.0.1:8000` | `pnpm dev` |
| Frontend dev server signed in to the backend (from `frontend/`) | `TOMARR_DEV_API_KEY="$(sed -n 's/^apikey = "\(.*\)"$/\1/p' "${TOMARR_CONFIG_DIR:-/config}/config.toml")" pnpm dev` |
| Frontend lint (from `frontend/`) | `pnpm lint` |
| Frontend types (from `frontend/`) | `pnpm typecheck` |
| Frontend tests (from `frontend/`) | `pnpm test` |
| Frontend build into `frontend/dist/` (from `frontend/`). Type checks first | `pnpm build` |
| Regenerate API types (planned for #13) | `pnpm gen:api` |
| Dev stack (Prowlarr, qBittorrent, SABnzbd, Suwayomi, Kavita) | `docker compose -f docker/docker-compose.dev.yml up` |

The dev server adds `X-Api-Key` to proxied `/api` requests when `TOMARR_DEV_API_KEY` is set. Read the key from `config.toml` with a command substitution as shown above, and never type it into a command. Vite reads it in `vite.config.ts` only, so it never reaches the bundle.
