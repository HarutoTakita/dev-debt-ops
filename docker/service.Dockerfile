# Multi-stage build for the service container (uv workspace member `rosetta-service`).
# Heavy-processing worker invoked by Cloud Tasks at /tasks/{pipeline} (issue 016/018).
# Targets: `dev` (hot-reload) and the default `runtime`. No frontend / SPA here.
# Playwright & other heavy deps are added in issue 018 when a pipeline needs them.

# ── Stage: builder (resolve + install rosetta-service deps from the workspace) ─
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/shared/pyproject.toml ./shared/pyproject.toml
COPY backend/shared/shared/ ./shared/shared/
COPY backend/service/pyproject.toml ./service/pyproject.toml
COPY backend/service/service/ ./service/service/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package rosetta-service

# ── Stage: base (common runtime layout: /app/service + /app/shared + venv) ────
FROM python:3.13-slim AS base
RUN useradd --create-home --uid 1001 appuser
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/shared /app/shared
COPY --from=builder --chown=appuser:appuser /app/service/service /app/service
USER appuser
EXPOSE 8000

# ── Stage: dev (hot-reload; service/ and shared/ are bind-synced by compose) ──
FROM base AS dev
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage: runtime (prod; default target) ─────────────────────────────────────
FROM base AS runtime
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
