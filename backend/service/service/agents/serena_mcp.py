"""Serena (LSP) MCP toolset for the Twin Agent (issue 069).

Serena is an LSP-backed MCP server that gives the agent *semantic* code navigation — find a symbol,
its references, implementations, and a file's symbol outline — so the specialists can target the
relevant code instead of reading files blindly via the REST tools (``build_repo_tools``).

Run as a separate stdio process (``serena start-mcp-server``) installed in its own isolated tool
env, so Serena's ``mcp`` dependency never conflicts with ``google-adk[mcp]`` (same approach as the
Semgrep MCP). Read-only / navigation tools only — editing / shell / memory tools are filtered out.
"""

from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

# Serena navigation tools we expose to the agent (editing / shell / memory / onboarding excluded).
_SERENA_TOOLS = [
    "find_symbol",
    "find_referencing_symbols",
    "find_declaration",
    "find_implementations",
    "get_symbols_overview",
    "list_dir",
    "find_file",
    "read_file",
    "search_for_pattern",
]


def build_serena_toolset(repo_dir: str) -> McpToolset:
    """Build the Serena MCP toolset pointed at an on-disk project tree (stdio, read-only nav tools).

    ``repo_dir`` is a checked-out repository (see ``services.repo_checkout``). Uses the ``ide``
    context + ``no-onboarding`` mode for non-interactive agent use, and the default LSP backend.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="serena",
                args=[
                    "start-mcp-server",
                    "--project",
                    repo_dir,
                    "--context",
                    "ide",
                    "--mode",
                    "no-onboarding",
                    "--transport",
                    "stdio",
                    "--enable-web-dashboard",
                    "false",
                ],
            ),
            # Serena's startup (agent init + LSP managers) takes ~5-6s; the default 5s connect
            # timeout races it and fails with BrokenResourceError. Give generous headroom.
            timeout=90.0,
        ),
        tool_filter=list(_SERENA_TOOLS),
    )
