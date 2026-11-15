# Node 22.22.2 is the floor set by Vitest 5.1 and jsdom 31 (CLAUDE.md, Approved dependencies).
# The build output is the same on every platform, so it runs once, natively, not under emulation.
FROM --platform=$BUILDPLATFORM node:22.23.5-slim AS frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /src/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.13-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:0.11.33 /uv /usr/local/bin/uv
# The venv is copied into the runtime stage at the same path, so its scripts keep working.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
# Not editable: system.py reads version("tomarr"), which needs the installed package.
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim
# 7zip-rar is in non-free, so the component is added to both stanzas of the deb822 sources file.
# The grep fails the build if the sed matched nothing.
RUN sed -i 's/^Components: main$/Components: main non-free/' /etc/apt/sources.list.d/debian.sources \
    && grep -q '^Components: main non-free$' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends 7zip 7zip-rar \
    && rm -rf /var/lib/apt/lists/*
COPY --from=backend /app/.venv /app/.venv
COPY --from=frontend /src/frontend/dist /app/frontend
COPY --chmod=755 docker/entrypoint.sh /app/entrypoint.sh
ENV PATH=/app/.venv/bin:$PATH \
    TOMARR_STATIC_DIR=/app/frontend
VOLUME /config
EXPOSE 6464
# The healthcheck fails until the app has written config.toml, so the start period covers a first
# start. One probe can take 6 seconds when the bind address is a wildcard (two 3 second probes).
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --start-interval=5s --retries=3 \
    CMD ["python", "-m", "tomarr", "healthcheck"]
ENTRYPOINT ["/app/entrypoint.sh"]
