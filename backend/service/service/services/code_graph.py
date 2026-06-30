"""CodeGraphContext (CGC) code-graph build for agentic analysis (issue 235).

Builds a code graph from a checked-out repository using the CGC CLI, so the Twin Agent's specialists
can then query macro structure (call chains, module dependencies, impact / blast-radius, dead code)
via the CGC MCP server (``agents.code_graph_mcp``) — complementing Serena's micro LSP navigation.

Design (validated by spike):
- CGC is an **isolated uv tool** on Python 3.12 with the **embedded KuzuDB** backend (no Neo4j). The
  backend is forced per-process via ``CGC_RUNTIME_DB_TYPE=kuzudb`` (the global ``.env`` may default to
  falkordb), so we never depend on writing config files.
- ``cgc index`` is synchronous; we shell out and bound it with a timeout.
- **Graceful**: any failure (binary missing, a file the alpha parser chokes on, timeout, non-zero rc)
  returns ``False`` so the agentic analysis continues without the graph. The graph DB is shared
  per-container; queries are scoped by the repo's on-disk path (the unique per-run clone dir).
"""

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

_INDEX_TIMEOUT = 300.0  # seconds; bounds a slow index on a large repo
_QUERY_TIMEOUT = 60.0  # seconds; bounds a snapshot extraction query
_SNAPSHOT_EDGE_LIMIT = 2000  # cap edges/nodes so the persisted snapshot stays bounded for the UI

# Force the embedded KuzuDB backend regardless of the global CGC .env default (which is falkordb and
# would need a separate service). The CLI and the MCP server both honour this runtime env var.
CGC_DB_ENV = {"CGC_RUNTIME_DB_TYPE": "kuzudb"}


def cgc_env() -> dict[str, str]:
    """Return the process env with the KuzuDB backend forced (shared by the CLI build + MCP server)."""
    return {**os.environ, **CGC_DB_ENV}


async def build_graph(repo_dir: str) -> bool:
    """Index ``repo_dir`` into the CGC code graph (synchronous CLI). Return ``True`` on success.

    Graceful: returns ``False`` (never raises) when ``cgc`` is unavailable, times out, or fails, so
    the caller can proceed without the graph.
    """
    if not repo_dir:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "cgc",
            "index",
            repo_dir,
            env=cgc_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        logger.warning("cgc not available; skipping code-graph build")
        return False
    try:
        async with asyncio.timeout(_INDEX_TIMEOUT):
            _stdout, stderr = await proc.communicate()
    except TimeoutError:
        proc.kill()
        logger.warning("cgc index timed out after %ss; skipping code-graph build", _INDEX_TIMEOUT)
        return False
    if proc.returncode != 0:
        logger.warning("cgc index failed (rc=%s): %s", proc.returncode, stderr.decode(errors="replace")[:500])
        return False
    logger.info("cgc index built code graph for %s", repo_dir)
    return True


async def _cgc_query(cypher: str) -> list[dict]:
    """Run one read-only ``cgc query`` (Cypher) and return its JSON rows (``[]`` on any failure)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "cgc",
            "query",
            cypher,
            env=cgc_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        return []
    try:
        async with asyncio.timeout(_QUERY_TIMEOUT):
            stdout, _stderr = await proc.communicate()
    except TimeoutError:
        proc.kill()
        return []
    text = stdout.decode(errors="replace")
    # The CLI prints the result as a JSON array on stdout (status/preamble go to stderr). Be tolerant
    # of any stray leading text by slicing to the outermost brackets before parsing.
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        rows = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict)]


async def extract_snapshot(repo_dir: str) -> dict:
    """Extract a compact node-link snapshot (function call graph) from the built CGC graph.

    Returns ``{"nodes": [{"id"}], "edges": [{"source","target"}]}`` for persistence so a future UI can
    render the code graph without re-indexing. Best-effort + bounded (``LIMIT``); returns ``{}`` on any
    failure so the caller persists an empty graph rather than breaking the run. ``repo_dir`` is accepted
    for future path-scoping; the current container indexes one repo per run.
    """
    if not repo_dir:
        return {}
    edges_rows = await _cgc_query(
        f"MATCH (a:Function)-[:CALLS]->(b:Function) RETURN a.name AS source, b.name AS target "
        f"LIMIT {_SNAPSHOT_EDGE_LIMIT}"
    )
    if not edges_rows:
        return {}
    edges = [{"source": r["source"], "target": r["target"]} for r in edges_rows if r.get("source") and r.get("target")]
    node_ids = {e["source"] for e in edges} | {e["target"] for e in edges}
    return {"nodes": [{"id": n} for n in sorted(node_ids)], "edges": edges}
