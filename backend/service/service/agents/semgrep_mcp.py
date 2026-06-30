"""Semgrep MCP toolset for the Twin Agent's code specialist (issue 069 / 204).

Connects the agent to the in-house Semgrep MCP server (``service.agents.semgrep_mcp_server``) over
stdio, exposing ``scan_code`` so the code-debt specialist can run real static analysis on files it
reads — the deterministic signal; the agent supplies the judgement. Launched with the current
interpreter so it shares the service venv (Semgrep + adk-compatible ``mcp``); no extra dependency or
network. Mirrors ``serena_mcp`` / ``trivy_mcp`` (separate stdio process, graceful when unavailable).
"""

import sys

from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters


def build_semgrep_toolset() -> McpToolset:
    """Build the Semgrep MCP toolset (in-house server over stdio) for the code-debt specialist."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "service.agents.semgrep_mcp_server"],
            ),
            # FastMCP server boot is quick, but give headroom over the default 5s connect timeout.
            timeout=30.0,
        ),
    )
