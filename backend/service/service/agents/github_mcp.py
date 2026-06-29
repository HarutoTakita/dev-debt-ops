"""GitHub MCP toolset for the Twin Agent (issue 069).

Adds a *process / history* signal axis to the agent's judgement: PR reviews (and whether code went
in unreviewed), commit/author history, and code-scanning / Dependabot alerts. Grounds knowledge-debt
(unreviewed, author churn) and technical-debt (security alerts) reasoning — no new persisted tables.

Runs the official ``github-mcp-server`` as a separate read-only stdio process (same isolation as the
Serena/Semgrep MCPs → no ``mcp`` version conflict with ``google-adk[mcp]``). Authenticated with the
run's minted GitHub App installation token, passed via env (never on argv). Only a focused set of
read tools is exposed via ``tool_filter`` to keep the agent's tool list small.
"""

import os

from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

# Read-only toolset groups to enable on the server (bounds what exists at all).
_GITHUB_TOOLSETS = "pull_requests,repos,code_security,dependabot"
# Focused subset exposed to the agent (the new "process/history" + "security alert" signals).
_GITHUB_TOOLS = [
    "list_pull_requests",
    "pull_request_read",
    "list_commits",
    "get_commit",
    "list_code_scanning_alerts",
    "get_code_scanning_alert",
    "list_dependabot_alerts",
    "get_dependabot_alert",
]


def build_github_toolset(token: str) -> McpToolset:
    """Build the GitHub MCP toolset (read-only stdio server authed with ``token``).

    ``token`` is the run's GitHub App installation token; it is passed via the
    ``GITHUB_PERSONAL_ACCESS_TOKEN`` env (not argv). Toolsets that the App lacks permission for
    (e.g. code scanning / Dependabot) simply 403 at call time — the agent ignores them (graceful).
    """
    env = {
        "GITHUB_PERSONAL_ACCESS_TOKEN": token,
        # mcp replaces the subprocess env wholesale when ``env`` is set, so carry PATH/HOME through.
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/home/appuser"),
    }
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="github-mcp-server",
                args=["stdio", "--read-only", "--toolsets", _GITHUB_TOOLSETS],
                env=env,
            ),
            timeout=90.0,
        ),
        tool_filter=list(_GITHUB_TOOLS),
    )
