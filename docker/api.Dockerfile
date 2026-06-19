# Multi-stage build for the api container (uv workspace member `rosetta-api`).
# Targets: `dev` (hot-reload; code bind-synced by `docker compose watch`) and the
# default `runtime` (prod: SPA baked in, migrations on boot). See issue 015.

# ── Stage: frontend (prod SPA bake) ───────────────────────────────────────────
FROM oven/bun:1 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

# ── Stage: builder (resolve + install rosetta-api deps from the workspace) ────
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Workspace root + shared (real package) + api (run from source).
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/shared/pyproject.toml ./shared/pyproject.toml
COPY backend/shared/shared/ ./shared/shared/
COPY backend/api/pyproject.toml ./api/pyproject.toml
COPY backend/api/app/ ./api/app/
COPY backend/api/alembic.ini ./api/alembic.ini

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package rosetta-api

# ── Stage: base (common runtime layout: /app/app + /app/shared + venv) ────────
FROM python:3.14-slim AS base
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/shared /app/shared
COPY --from=builder /app/api/app /app/app
COPY --from=builder /app/api/alembic.ini /app/alembic.ini
EXPOSE 8000

# ── Stage: dev (hot-reload; app/ and shared/ are bind-synced by compose) ──────
FROM base AS dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage: runtime (prod; default target) — bake SPA, migrate on boot ─────────
FROM base AS runtime
ENV ENVIRONMENT=prod
COPY --from=frontend /app/build /app/app/static
# `alembic upgrade head` is idempotent and takes an advisory lock, so concurrent
# replicas serialize safely.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
