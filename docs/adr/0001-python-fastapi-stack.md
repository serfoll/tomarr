# 0001: Python and FastAPI backend, Vite React frontend

Status: accepted, November 2026

## Context

Most *arr apps are C#, inherited from the Sonarr codebase through forks. Forking Readarr would give auth, a task queue, download clients and native Prowlarr sync on day one, but its author-and-book model fits series, editions, volumes and chapters poorly, and Readarr is retired. Go would give the smallest footprint (Librarr runs as one small binary with low idle memory).

The workload is I/O-bound: metadata Providers, Prowlarr, download clients and Gemini, all behind rate limits. The CPU work (regex parsing, fuzzy matching through rapidfuzz, zip and image handling) is fast enough in Python.

## Decision

Python 3.13 with FastAPI, Pydantic v2, SQLAlchemy 2.0 and SQLite. A React and TypeScript single-page app built with Vite and served by FastAPI as static files. One container.

## Consequences

- Fastest path to shipping in the maintainer's strongest languages, and the best ergonomics for Gemini structured output (Pydantic models as response schemas).
- Heavier than Go: expect an image around 200 MB and roughly 100 MB of RAM idle. Tomarr does not compete on footprint.
- No Next.js: there's no server rendering need, and a static build keeps the image to one runtime.
