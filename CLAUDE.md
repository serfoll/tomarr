# Tomarr

Tomarr is a self-hosted *arr for manga, manhwa and webtoons. It tracks series down to volumes and chapters, finds releases through Prowlarr (with Suwayomi as an optional fallback for single chapters), sends them to a download client, imports them with clean metadata and tells Kavita to rescan.

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

- Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.0 (typed) with Alembic, SQLite in WAL mode, httpx (async). Package manager: uv. Lint and format: ruff. Types: pyright. Tests: pytest with recorded HTTP fixtures.
- Frontend: React and TypeScript in a Vite SPA, TanStack Router, Query and Table. API client generated from the backend's OpenAPI schema. Package manager: pnpm. Lint and format: Biome. Tests: Vitest.
- LLM: Google Gemini through the official `google-genai` SDK, bring your own key, behind a provider interface.
- Shipping: one Docker image (multi-arch amd64 and arm64) published to GHCR. Config and database live in `/config`.
- License: AGPL-3.0.

Design (colors, type, components) is not decided yet. Don't invent a design system; use unstyled headless primitives until `CONTEXT/design/` exists.

## Commands

The project is not scaffolded yet. These are the commands the scaffold should provide. Until a command exists in `pyproject.toml` or `package.json`, don't reference it as if it does.

| Task | Command |
|---|---|
| Backend tests | `uv run pytest` |
| Backend lint and types | `uv run ruff check . && uv run ruff format --check . && uv run pyright` |
| Frontend lint | `pnpm lint` |
| Frontend tests | `pnpm test` |
| Regenerate API types | `pnpm gen:api` |
| Dev stack (Prowlarr, qBittorrent, SABnzbd, Suwayomi, Kavita) | `docker compose -f docker/docker-compose.dev.yml up` |
