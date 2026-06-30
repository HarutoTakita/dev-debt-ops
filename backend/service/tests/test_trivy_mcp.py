"""issue 069: Trivy MCP toolset builder — construction only (no process spawned)."""

from google.adk.tools.mcp_tool import McpToolset

from service.agents import trivy_mcp


def test_build_trivy_toolset_shape() -> None:
    ts = trivy_mcp.build_trivy_toolset()
    assert isinstance(ts, McpToolset)
    sp = ts._connection_params.server_params
    assert sp.command == "trivy"
    assert sp.args == ["mcp", "-t", "stdio"]
    # HOME is carried through so Trivy finds its plugin (~/.trivy) + DB cache (~/.cache/trivy).
    assert "HOME" in sp.env


def test_trivy_tool_filter_is_scan_only() -> None:
    # findings_list / findings_get are excluded: the installed trivy-mcp plugin panics in its
    # ListHandler (nil→string interface conversion), so only scan_filesystem is exposed.
    assert trivy_mcp._TRIVY_TOOLS == ["scan_filesystem"]
