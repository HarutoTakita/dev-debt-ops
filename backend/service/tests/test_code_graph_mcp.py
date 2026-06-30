"""issue 235: CodeGraphContext MCP toolset builder — construction only (no process spawned)."""

from google.adk.tools.mcp_tool import McpToolset

from service.agents import code_graph_mcp


def test_build_code_graph_toolset_shape() -> None:
    ts = code_graph_mcp.build_code_graph_toolset()
    assert isinstance(ts, McpToolset)
    sp = ts._connection_params.server_params
    assert sp.command == "codegraphcontext"
    assert sp.args == ["mcp", "start"]
    # 埋め込み KuzuDB を強制（グローバル .env 既定の falkordb を上書き）し DB パスを固定、PATH/HOME を渡す。
    assert sp.env["CGC_RUNTIME_DB_TYPE"] == "kuzudb"
    assert sp.env.get("KUZUDB_PATH")  # 明示パスを固定（HOME 未設定でも /app 配下に作らない）
    # HOME は空文字でないこと（空だと CGC の Path.home() が CWD 相対 → PermissionError [Errno 13]）。
    assert sp.env.get("HOME")
    assert "PATH" in sp.env


def test_cgc_tool_filter_is_query_only() -> None:
    # 索引(add_code)/watch/delete/raw cypher は除外（パイプラインがグラフを構築）。高レベル照会系のみ。
    tools = code_graph_mcp._CGC_TOOLS
    assert "analyze_code_relationships" in tools
    assert all(("add_code" not in t and "watch" not in t and "delete" not in t and "cypher" not in t) for t in tools)
