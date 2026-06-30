"""CodeGraphContext (CGC) MCP toolset for the Twin Agent (issue 235).

Connects the agent to the CGC MCP server (``codegraphcontext mcp start``, stdio) so the specialists
can query the **macro** code graph the pipeline built (``services.code_graph.build_graph``): call
chains, module dependencies, impact / blast-radius, class hierarchy, dead code, complexity hotspots.
This complements Serena's **micro** LSP navigation — graph for "where to look / what's affected",
LSP for "read/edit precisely".

Isolated uv tool on Python 3.12 with the embedded KuzuDB backend (no Neo4j); the backend is forced
via ``CGC_RUNTIME_DB_TYPE=kuzudb`` in the env (see ``services.code_graph.CGC_DB_ENV``). Read/analysis
tools only — indexing / watch / delete tools are excluded because the pipeline owns graph building.
"""

import os

from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

from service.services.code_graph import CGC_DB_ENV, CGC_HOME

# CGC analysis/query tools exposed to the agent (indexing/watch/delete/cypher excluded — the pipeline
# builds the graph; raw Cypher is withheld to keep the agent on the high-level analysis API).
_CGC_TOOLS = [
    "analyze_code_relationships",
    "find_code",
    "find_dead_code",
    "find_most_complex_functions",
    "get_repository_stats",
    "list_indexed_repositories",
]


def build_code_graph_toolset() -> McpToolset:
    """Build the CGC MCP toolset (stdio, embedded KuzuDB) for the Twin Agent's specialists.

    The agent passes the repository path (the checked-out clone dir) as ``repo_path`` in tool args to
    scope queries — the same dir the pipeline indexed. Setting ``env`` replaces the child env wholesale,
    so ``PATH`` is carried through and ``HOME`` is the resolved ``CGC_HOME`` (never the empty string —
    an empty HOME makes CGC's ``Path.home()`` resolve under CWD and fail with PermissionError). ``CGC_DB_ENV``
    forces the embedded KuzuDB backend + pinned path so the server reads the same graph the CLI built.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="codegraphcontext",
                args=["mcp", "start"],
                env={
                    **CGC_DB_ENV,
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": CGC_HOME,
                },
            ),
            timeout=90.0,
        ),
        tool_filter=list(_CGC_TOOLS),
    )
