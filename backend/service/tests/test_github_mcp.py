"""issue 069: GitHub MCP toolset builder — construction only (no process spawned)."""

from google.adk.tools.mcp_tool import McpToolset

from service.agents import github_mcp


def test_build_github_toolset_shape() -> None:
    ts = github_mcp.build_github_toolset("tok-123")
    assert isinstance(ts, McpToolset)
    sp = ts._connection_params.server_params  # stdio server params
    assert sp.command == "github-mcp-server"
    assert "stdio" in sp.args
    assert "--read-only" in sp.args  # never expose write tools
    # Auth via env, not argv (token must not leak onto the command line).
    assert sp.env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "tok-123"
    assert "tok-123" not in sp.args


def test_github_tool_filter_is_focused_read_only() -> None:
    # Only the process/history + security-alert read tools we want, no write/PR-merge tools.
    assert "list_pull_requests" in github_mcp._GITHUB_TOOLS
    assert "list_code_scanning_alerts" in github_mcp._GITHUB_TOOLS
    assert "list_dependabot_alerts" in github_mcp._GITHUB_TOOLS
    assert not any("create" in t or "merge" in t for t in github_mcp._GITHUB_TOOLS)
