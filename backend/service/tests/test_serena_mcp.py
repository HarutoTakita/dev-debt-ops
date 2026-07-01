"""issue 069/266: Serena MCP toolset builder — construction only (no process spawned)."""

import pytest
from google.adk.tools.mcp_tool import McpToolset

from service.agents import serena_mcp


def test_build_serena_toolset_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serena_mcp.shutil, "which", lambda _cmd: "/usr/bin/serena")
    ts = serena_mcp.build_serena_toolset("/tmp/repo")
    assert isinstance(ts, McpToolset)
    sp = ts._connection_params.server_params  # stdio server params
    assert sp.command == "serena"
    assert "start-mcp-server" in sp.args
    assert "/tmp/repo" in sp.args  # pointed at the checked-out project tree


def test_build_serena_toolset_absent_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Missing binary → None (graceful): the Base Analysis run must not fail because Serena is absent.
    monkeypatch.setattr(serena_mcp.shutil, "which", lambda _cmd: None)
    assert serena_mcp.build_serena_toolset("/tmp/repo") is None


def test_serena_tool_filter_is_navigation_only() -> None:
    # Read-only semantic navigation; editing/shell/memory tools are never exposed.
    assert "find_symbol" in serena_mcp._SERENA_TOOLS
    assert "get_symbols_overview" in serena_mcp._SERENA_TOOLS
    assert not any(("edit" in t or "shell" in t or "write" in t or "memory" in t) for t in serena_mcp._SERENA_TOOLS)
