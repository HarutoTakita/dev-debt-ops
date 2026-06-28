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
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

# System deps for Serena (LSP) repo navigation (issue 069):
#  - git: shallow-clone the analysed repo to disk (services.repo_checkout)
#  - Node 20: runtime for Serena's TypeScript language server (auto-downloaded into ~/.serena) and
#    for pyright (the Python LS, launched via `uvx`). Serena manages the LS binaries itself.
#  - serena-agent: installed as an isolated uv tool (its own deps → no `mcp` conflict with adk[mcp]).
# Installed into world-readable locations (/usr/local/bin, /opt/uv) so the unprivileged appuser can run them.
ENV UV_TOOL_DIR=/opt/uv/tools UV_TOOL_BIN_DIR=/usr/local/bin
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && uv tool install -p 3.13 serena-agent \
    # Serena launches its Python LS (pyright) via `uvx`; uv 0.9.x ships no `uvx` here and its
    # `uv x` fallback is an invalid subcommand → provide a uvx shim (uvx == `uv tool run`).
    && printf '#!/bin/sh\nexec uv tool run "$@"\n' > /usr/local/bin/uvx && chmod 0755 /usr/local/bin/uvx \
    && chmod -R a+rX /opt/uv \
    && apt-get purge -y curl && apt-get autoremove -y && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache /root/.npm

RUN useradd --create-home --uid 1001 appuser
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/shared /app/shared
COPY --from=builder --chown=appuser:appuser /app/service/service /app/service
USER appuser
# Pre-warm Serena's Python LS (pyright) into appuser's uv cache so the first analysis doesn't
# download it mid-run (avoids the connect-timeout race). Best-effort: runtime works regardless.
RUN printf '' | timeout 180 uvx -p 3.13 --from pyright==1.1.403 pyright-langserver --stdio || true
EXPOSE 8000

# ── Stage: dev (hot-reload; service/ and shared/ are bind-synced by compose) ──
FROM base AS dev
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage: runtime (prod; default target) ─────────────────────────────────────
FROM base AS runtime
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
