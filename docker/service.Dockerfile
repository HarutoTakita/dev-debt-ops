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
# GitHub MCP server binary (issue 069): the agent's process/history + security-alert signal axis.
COPY --from=ghcr.io/github/github-mcp-server /server/github-mcp-server /usr/local/bin/github-mcp-server

# System deps for Serena (LSP) repo navigation (issue 069):
#  - git: shallow-clone the analysed repo to disk (services.repo_checkout)
#  - Node 20: runtime for Serena's TypeScript language server (auto-downloaded into ~/.serena) and
#    for pyright (the Python LS, launched via `uvx`). Serena manages the LS binaries itself.
#  - serena-agent: installed as an isolated uv tool (its own deps → no `mcp` conflict with adk[mcp]).
#  - codegraphcontext (CGC, issue 235): code-graph MCP for macro structure (call chains / module
#    deps / impact / dead code). Installed as an isolated uv tool ON PYTHON 3.12 (its
#    tree-sitter-language-pack is incompatible with 3.13 and it pins protobuf<3.21 — both would
#    conflict with the service venv), with the embedded KuzuDB backend (`--with kuzu`, no Neo4j).
# Installed into world-readable locations (/usr/local/bin, /opt/uv) so the unprivileged appuser can run them.
# UV_PYTHON_INSTALL_DIR も /opt/uv 配下へ固定する: `-p 3.12` はベースイメージに無いため uv が管理 CPython を
# DL するが、既定では root ホーム (/root/.local/share/uv/python, mode 700) に置かれ、CGC のシェバンがそこを指す。
# appuser (uid1001) は /root を辿れずインタプリタ起動が Errno 13 Permission denied → CGC MCP 全滅 → Twin Agent が
# `analyze_code_relationships` 未登録で失敗する。world-readable な /opt/uv/python へ移し、直後の chmod で権限も付与（issue 235）。
ENV UV_TOOL_DIR=/opt/uv/tools UV_TOOL_BIN_DIR=/usr/local/bin UV_PYTHON_INSTALL_DIR=/opt/uv/python
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && uv tool install -p 3.13 serena-agent \
    && uv tool install -p 3.12 codegraphcontext --with kuzu \
    # Serena launches its Python LS (pyright) via `uvx`; uv 0.9.x ships no `uvx` here and its
    # `uv x` fallback is an invalid subcommand → provide a uvx shim (uvx == `uv tool run`).
    && printf '#!/bin/sh\nexec uv tool run "$@"\n' > /usr/local/bin/uvx && chmod 0755 /usr/local/bin/uvx \
    && chmod -R a+rX /opt/uv \
    # Trivy (issue 069 → 278): SCA / secrets / misconfig signal axis. Run as a deterministic CLI block
    # (services.trivy_scan → code_debts); the `trivy mcp` plugin was dropped with the Twin Agent.
    && curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin v0.71.2 \
    && apt-get purge -y curl && apt-get autoremove -y && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache /root/.npm

RUN useradd --create-home --uid 1001 appuser
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
# Docker does not export HOME for a non-root USER, so set it explicitly. Tools that write under ~ —
# Serena (~/.serena), Trivy (~/.trivy, ~/.cache/trivy) and CodeGraphContext (~/.codegraphcontext, its
# embedded KuzuDB) — must resolve to appuser's writable home. With HOME unset/empty, CGC's Path.home()
# resolves under CWD (/app, root-owned) and dies with PermissionError [Errno 13]; pin it once here.
ENV HOME=/home/appuser
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/shared /app/shared
COPY --from=builder --chown=appuser:appuser /app/service/service /app/service
USER appuser
# Pre-warm runtimes into appuser caches so the first analysis doesn't download mid-run
# (avoids the connect-timeout race). All best-effort: runtime works regardless.
#  - Serena's Python LS (pyright) into the uv cache
#  - Trivy's vulnerability/secret/misconfig DBs (~/.cache/trivy) for the deterministic CLI scan
RUN printf '' | timeout 180 uvx -p 3.13 --from pyright==1.1.403 pyright-langserver --stdio || true
RUN mkdir -p /tmp/trivy-warm && printf '{}' > /tmp/trivy-warm/package.json \
    && timeout 300 trivy fs --scanners vuln,secret,misconfig --quiet /tmp/trivy-warm || true \
    && rm -rf /tmp/trivy-warm
EXPOSE 8000

# ── Stage: dev (hot-reload; service/ and shared/ are bind-synced by compose) ──
FROM base AS dev
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage: runtime (prod; default target) ─────────────────────────────────────
FROM base AS runtime
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
