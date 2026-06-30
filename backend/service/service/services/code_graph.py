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
_SNAPSHOT_EDGE_LIMIT = 2000  # cap file↔file edges so the persisted snapshot stays bounded for the UI
_SNAPSHOT_FN_LIMIT = 8000  # cap function nodes / intra-file call edges (Level-3 lazy view, issue 240)

# Resolve a writable HOME explicitly. The unprivileged container user (appuser) has no HOME set, and
# CGC stores its embedded KuzuDB under ``<home>/.codegraphcontext/global/kuzudb`` (created on startup).
# With HOME unset/empty, ``Path.home()`` resolves relative to CWD (``/app``, root-owned → not writable)
# and CGC dies with ``PermissionError [Errno 13]`` — which is the failure the MCP server hit when its
# env carried ``HOME=""``. Pin HOME here so the CLI build and the MCP server agree on one location.
CGC_HOME = os.environ.get("HOME") or "/home/appuser"

# Force the embedded KuzuDB backend regardless of the global CGC .env default (which is falkordb and
# would need a separate service), and pin its on-disk path so it never depends on Path.home(). The CLI
# build and the MCP server both honour these runtime env vars (shared via ``CGC_DB_ENV`` / ``cgc_env``).
CGC_DB_ENV = {
    "CGC_RUNTIME_DB_TYPE": "kuzudb",
    "KUZUDB_PATH": os.path.join(CGC_HOME, ".codegraphcontext", "global", "kuzudb"),
}


def cgc_env() -> dict[str, str]:
    """Return the process env with the KuzuDB backend + path forced and a writable HOME (CLI + MCP)."""
    return {**os.environ, **CGC_DB_ENV, "HOME": CGC_HOME}


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
    """Extract a node-link snapshot from the built CGC graph (issue 238 / 240).

    Returns ``{"file_edges": [...], "functions": [...], "function_calls": [...]}`` for persistence:
    - ``file_edges`` (Level-2): cross-file function calls aggregated to files
      (``File-[:CONTAINS]->Function-[:CALLS]->Function<-[:CONTAINS]-File``) — the feature's file subgraph.
    - ``functions`` / ``function_calls`` (Level-3, issue 240): per-file functions and intra-file call
      edges, for the on-demand file drilldown.
    CGC's ``File.relative_path`` is repo-relative, matching ``file_kc`` paths so the frontend joins by
    path. The three layers are extracted **independently** (a repo may have intra-file functions but no
    cross-file calls, or vice versa). Best-effort + bounded (``LIMIT``); returns ``{}`` only when all
    three are empty so the caller persists nothing (keeping a prior snapshot) rather than breaking the
    run. ``repo_dir`` is accepted for future path-scoping; the current container indexes one repo per run.
    """
    if not repo_dir:
        return {}
    # The three layers are extracted INDEPENDENTLY: a repo can have intra-file functions (Level-3)
    # without any cross-file calls (Level-2 file_edges), and vice versa. Gating functions on file_edges
    # (the previous behaviour) meant small repos with no cross-file CALLS persisted nothing, so the map
    # never showed CGC structure. Persist whatever exists; return {} only when ALL three are empty.
    edge_rows = await _cgc_query(
        "MATCH (af:File)-[:CONTAINS]->(:Function)-[:CALLS]->(:Function)<-[:CONTAINS]-(bf:File) "
        "WHERE af.relative_path <> bf.relative_path "
        f"RETURN DISTINCT af.relative_path AS source, bf.relative_path AS target LIMIT {_SNAPSHOT_EDGE_LIMIT}"
    )
    edges = [{"source": r["source"], "target": r["target"]} for r in edge_rows if r.get("source") and r.get("target")]

    # Level-3 (issue 240): per-file functions + intra-file call edges, for the on-demand file drilldown.
    # `<module>` is CGC's file-level pseudo-function — excluded so the graph shows real functions only.
    fn_rows = await _cgc_query(
        "MATCH (f:File)-[:CONTAINS]->(fn:Function) WHERE fn.name <> '<module>' "
        f"RETURN DISTINCT f.relative_path AS file, fn.name AS name LIMIT {_SNAPSHOT_FN_LIMIT}"
    )
    call_rows = await _cgc_query(
        "MATCH (f:File)-[:CONTAINS]->(a:Function)-[:CALLS]->(b:Function)<-[:CONTAINS]-(f) "
        "WHERE a.name <> '<module>' AND b.name <> '<module>' AND a.name <> b.name "
        f"RETURN DISTINCT f.relative_path AS file, a.name AS source, b.name AS target LIMIT {_SNAPSHOT_FN_LIMIT}"
    )
    functions = [{"file": r["file"], "name": r["name"]} for r in fn_rows if r.get("file") and r.get("name")]
    function_calls = [
        {"file": r["file"], "source": r["source"], "target": r["target"]}
        for r in call_rows
        if r.get("file") and r.get("source") and r.get("target")
    ]
    if not edges and not functions and not function_calls:
        return {}
    return {"file_edges": edges, "functions": functions, "function_calls": function_calls}


def merge_snapshots(cgc: dict, det: dict) -> dict:
    """Merge the CGC snapshot with a deterministic fallback (``function_graph.build_snapshot``).

    CGC is preferred where it has data; the deterministic snapshot fills the gaps so L3 (and L2
    ``file_edges``) display for any analysed repo even when CGC failed to index or returned nothing
    (issue 250). ``file_edges`` is chosen independently, but ``functions``/``function_calls`` are
    chosen **as a pair** from the same source (their names must be consistent for L3 to render).
    Returns ``{}`` when both snapshots are empty.
    """
    cgc = cgc or {}
    det = det or {}
    file_edges = cgc.get("file_edges") or det.get("file_edges") or []
    if cgc.get("functions"):
        functions = cgc.get("functions") or []
        function_calls = cgc.get("function_calls") or []
    else:
        functions = det.get("functions") or []
        function_calls = det.get("function_calls") or []
    if not file_edges and not functions and not function_calls:
        return {}
    return {"file_edges": file_edges, "functions": functions, "function_calls": function_calls}
