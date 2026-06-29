"""Trivy MCP toolset for the Twin Agent (issue 069).

Adds a *supply-chain / security* signal axis: vulnerable dependencies (SCA), leaked secrets, and
misconfigurations — a debt axis the existing detectors (Serena/LSP, Semgrep, import graph) don't
cover. Grounds the code specialist's judgement; findings surface in ``agent_trace`` /
``recommendations`` (no new persisted tables).

Runs Trivy's MCP plugin (``trivy mcp``) as a separate stdio process (isolation → no ``mcp`` version
conflict). The agent scans the already-checked-out repo via ``scan_filesystem`` (the clone path is
injected into the code specialist's instruction by ``twin.py``). Fully local; no account needed.
"""

import os

from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

# Only ``scan_filesystem`` — it runs the scan and returns the findings inline, which is the whole
# signal we want. The findings-cache tools (``findings_list`` / ``findings_get``) are excluded
# because the installed trivy-mcp plugin panics in its ListHandler ("interface conversion:
# interface {} is nil, not string", pkg/tools/result/findings.go:59), crashing the stdio server
# and closing the connection on every call. Image / remote-repo scanners are excluded too.
_TRIVY_TOOLS = ["scan_filesystem"]


def build_trivy_toolset() -> McpToolset:
    """Build the Trivy MCP toolset (``trivy mcp`` over stdio, filesystem-scan tools only)."""
    env = {
        # mcp replaces the subprocess env wholesale when ``env`` is set; Trivy needs PATH to resolve
        # the binary and HOME for its plugin dir (~/.trivy) + vuln DB cache (~/.cache/trivy).
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/home/appuser"),
    }
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="trivy",
                args=["mcp", "-t", "stdio"],
                env=env,
            ),
            timeout=90.0,
        ),
        tool_filter=list(_TRIVY_TOOLS),
    )
