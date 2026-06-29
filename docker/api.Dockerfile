# Multi-stage build for the api container (uv workspace member `rosetta-api`).
# Targets: `dev` (hot-reload; code bind-synced by `docker compose watch`) and the
# default `runtime` (prod: SPA baked in, migrations on boot). See issue 015.

# ── Stage: frontend (prod SPA bake) ───────────────────────────────────────────
FROM oven/bun:1 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ .
# 変更履歴ビューア用: repo ルートの CHANGELOG.md を静的アセットとして同梱（/CHANGELOG.md で配信）。
# ビルドコンテキストは repo ルートなので参照可能。build スクリプトの sync:changelog はここでは no-op。
COPY CHANGELOG.md ./static/CHANGELOG.md
RUN bun run build

# ── Stage: builder (resolve + install rosetta-api deps from the workspace) ────
FROM python:3.13-slim AS builder
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
FROM python:3.13-slim AS base
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
# Apply migrations on boot — the dev DB volume is often recreated, so tables would
# otherwise be missing (login etc. 500s on `relation "users" does not exist`).
# compose `depends_on: db` is startup-order only (podman/WSL2 healthcheck timers don't
# fire → no service_healthy gate), so the DB may not accept connections yet: retry
# `alembic upgrade head` until it succeeds, then exec the reloader. `upgrade head` is
# idempotent, so this is a no-op once the schema is current.
CMD ["sh", "-c", "for i in $(seq 1 30); do alembic upgrade head && break; echo \"alembic upgrade head failed (attempt $i/30); waiting for db...\"; sleep 2; done; exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# ── Stage: runtime (prod; default target) — bake SPA, migrate on boot ─────────
FROM base AS runtime
ENV ENVIRONMENT=prod
COPY --from=frontend /app/build /app/app/static
# `alembic upgrade head` is idempotent and takes an advisory lock, so concurrent
# replicas serialize safely.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
