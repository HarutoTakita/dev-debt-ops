"""Serena (LSP) MCP toolset for the Twin Agent (issue 069).

Serena is an LSP-backed MCP server that gives the agent *semantic* code navigation — find a symbol,
its references, implementations, and a file's symbol outline — so the specialists can target the
relevant code instead of reading files blindly via the REST tools (``build_repo_tools``).

Run as a separate stdio process (``serena start-mcp-server``) installed in its own isolated tool
env, so Serena's ``mcp`` dependency never conflicts with ``google-adk[mcp]`` (same approach as the
Semgrep MCP). Read-only / navigation tools only — editing / shell / memory tools are filtered out.
"""

import logging
import shutil

from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

logger = logging.getLogger(__name__)

# Serena *semantic-navigation* tools we expose (editing / shell / memory / onboarding excluded).
# Deliberately NOT exposed: read_file / list_dir / find_file — these duplicate the repo tools
# (``build_repo_tools``) whose read_file is length-capped, whereas Serena's read_file returns the
# full untruncated file. Keeping only symbol-level navigation forces the agent to target relevant
# code (and pull large file bodies via the truncated repo tool), bounding the agent's context.
_SERENA_TOOLS = [
    "find_symbol",
    "find_referencing_symbols",
    "find_declaration",
    "find_implementations",
    "get_symbols_overview",
    "search_for_pattern",
]


def build_serena_toolset(repo_dir: str) -> McpToolset | None:
    """Build the Serena MCP toolset pointed at an on-disk project tree (stdio, read-only nav tools).

    ``repo_dir`` is a checked-out repository (see ``services.repo_checkout``). Uses the ``ide``
    context + ``no-onboarding`` mode for non-interactive agent use, and the default LSP backend.

    Returns ``None`` when the ``serena`` binary is not on PATH so a missing MCP server is truly
    *graceful* (toolset absent) instead of crashing the whole Base Analysis run when the agent first
    invokes a Serena tool (stdio MCP servers connect lazily → a missing binary otherwise raises
    mid-run and fails "コードベース探索"). Deterministic blocks and the REST repo tools are unaffected.
    """
    if shutil.which("serena") is None:
        logger.warning("serena binary not found on PATH; skipping Serena MCP toolset (graceful)")
        return None
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
