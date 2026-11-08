# Code standards

Code shape rules for this repo, scoped to what the linters don't already enforce. Formatting and lint mechanics belong to ruff (`pyproject.toml`) and Biome (`biome.json`).

## Python

- Type hints on every function signature. pyright runs in strict mode on `src/tomarr`. No `Any`; use `object` or a `Protocol` and narrow it.
- Pydantic models for API schemas and settings. SQLAlchemy models for the database. Don't use one as the other.
- All network and file I/O is async. Blocking work (archive extraction, image conversion) runs through `asyncio.to_thread`.
- Outbound HTTP goes through the client factory in `core/http.py`. Never create an `httpx.AsyncClient` anywhere else.
- No `print`. Use the module logger from `core/logging.py`.
- Exceptions: raise the domain errors in `core/errors.py` (`ProviderError`, `RateLimited`, `ParseError`, ...). Catch broad exceptions only at a Command or request boundary, and log them there.
- Settings and secrets are read through the settings service, never from `os.environ` directly outside `core/config.py`.
- File names are snake_case. One adapter per package (`providers/rakuten/`), with `client.py` for HTTP and `mapper.py` for converting responses into Tomarr types.

## Database

- Every schema change is an Alembic migration, generated and then read by a person before commit.
- Queries live in services or repository functions, never in routes or adapters.
- Enable SQLite WAL mode and foreign keys at connection time. Keep transactions short; don't hold one open across a network call.

## TypeScript

- Function components only. One component per file, kebab-case file names.
- `interface` for props and object shapes, `type` for unions. No `any`.
- All API calls go through the generated client in `src/api/`. Never write a request by hand or edit generated files. Regenerate after any backend schema change.
- Server state lives in TanStack Query. Local UI state stays in the component. No global store until a real need shows up.
- Import through the `@/*` alias, never deep relative paths.

## API

- REST under `/api/v1`, resources in plural nouns (`/series`, `/series/{id}/volumes`).
- Validate input with Pydantic before it reaches a service.
- Status codes: `200`/`201` success, `400` validation, `401` missing or wrong key, `404` not found, `409` conflict (series already added), `500` only for the unexpected.
- Never return stack traces, database errors or third-party error bodies to the client.
- Every endpoint appears in the OpenAPI schema with a response model, because the frontend client is generated from it.

## Readability

- Names say what the code does. A function that needs a comment to explain its purpose needs a better name.
- Same logic in two places gets extracted on the second use.
- One responsibility per function or module. A file past 200 lines is a sign it's doing more than one job.
- Match the solution's complexity to the problem's.

## Tests

- Backend tests live in `backend/tests/` at the path mirroring their source (`src/tomarr/parser/volume.py` → `tests/parser/test_volume.py`). Frontend tests live next to the mirror path under `frontend/tests/`.
- No live network in tests. HTTP is recorded once with `pytest-recording` into cassettes under `tests/fixtures/cassettes/` and replayed. Network access is blocked during test runs. Cassettes have API keys and tokens filtered out before they're written.
- The parser is tested against a golden corpus: `tests/fixtures/releases/*.yaml`, each entry a real release name and its expected Parsed release. Add a case for every parser bug before fixing it.
- Gemini calls are tested through recorded cassettes for the adapter, and through a fake LLM provider for everything that depends on the interface.
- Shared fixtures and fakes live in `tests/helpers/` (or `conftest.py` at the right level). Move a helper there when a second test file needs it.
- Every test has to be able to fail: it asserts something observable. Before a test counts as done, break the code it covers and watch it go red.
- No duplicate tests. If one test's assertions are a subset of another's, delete it.
- Test names and comments describe what the code does today, not its history.
