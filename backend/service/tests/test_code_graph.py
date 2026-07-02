"""issue 235: CGC code-graph build — graceful subprocess wrapper (no real `cgc` invoked)."""

import pytest

from service.services import code_graph


class _FakeProc:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        return (b"", b"boom")

    def kill(self) -> None:
        self.killed = True


def _patch_exec(monkeypatch: pytest.MonkeyPatch, proc: object) -> None:
    async def _fake_exec(*_args: object, **_kwargs: object) -> object:
        return proc

    monkeypatch.setattr(code_graph.asyncio, "create_subprocess_exec", _fake_exec)


def test_cgc_env_forces_kuzudb() -> None:
    """The shared env forces the embedded KuzuDB backend (no Neo4j)."""
    assert code_graph.cgc_env()["CGC_RUNTIME_DB_TYPE"] == "kuzudb"


async def test_build_graph_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_exec(monkeypatch, _FakeProc(0))
    assert await code_graph.build_graph("/tmp/repo") is True


async def test_build_graph_nonzero_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_exec(monkeypatch, _FakeProc(1))
    assert await code_graph.build_graph("/tmp/repo") is False


async def test_build_graph_missing_binary_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(code_graph.asyncio, "create_subprocess_exec", _boom)
    assert await code_graph.build_graph("/tmp/repo") is False


async def test_build_graph_empty_repo_dir_returns_false() -> None:
    assert await code_graph.build_graph("") is False


async def test_extract_snapshot_builds_file_and_function_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_query(cypher: str) -> list[dict]:
        if "CONTAINS]->(a:Function)-[:CALLS]" in cypher:  # function calls with both files (issue 282)
            return [{"source_file": "mod.py", "source": "a", "target_file": "util.py", "target": "b"}]  # cross-file
        if "CONTAINS]->(fn:Function)" in cypher:  # per-file functions (Level-3 nodes)
            return [{"file": "mod.py", "name": "a"}, {"file": "util.py", "name": "b"}]
        if "IMPORTS]->(m:Module)" in cypher:  # file→module imports (full specifier, resolved below)
            return [{"source": "app.py", "module": "./util"}]  # app.py imports ./util → util.py
        if "RETURN DISTINCT f.relative_path AS path" in cypher:  # repo file list (for stem resolution)
            return [{"path": "app.py"}, {"path": "mod.py"}, {"path": "util.py"}]
        return [{"source": "app.py", "target": "mod.py"}]  # cross-file CALLS (Level-2 edges)

    monkeypatch.setattr(code_graph, "_cgc_query", _fake_query)
    snap = await code_graph.extract_snapshot("/tmp/repo")
    # file_edges = CALLS (app.py→mod.py) ∪ resolved IMPORTS (app.py→util.py via unique stem "util").
    assert {"source": "app.py", "target": "mod.py"} in snap["file_edges"]
    assert {"source": "app.py", "target": "util.py"} in snap["file_edges"]
    assert {"file": "mod.py", "name": "a"} in snap["functions"]
    # cross-file call kept with both endpoints' files (previously collapsed away into file_edges).
    assert {"source_file": "mod.py", "source": "a", "target_file": "util.py", "target": "b"} in snap["function_calls"]


async def test_extract_snapshot_keeps_functions_without_cross_file_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    """A repo with intra-file functions but NO cross-file calls must still persist the Level-3 graph
    (functions/function_calls), not return {} — otherwise the map never shows CGC structure (issue 248)."""

    async def _fake_query(cypher: str) -> list[dict]:
        if "CONTAINS]->(a:Function)-[:CALLS]" in cypher:  # intra-file calls present
            return [{"source_file": "mod.py", "source": "a", "target_file": "mod.py", "target": "b"}]
        if "CONTAINS]->(fn:Function)" in cypher:  # functions present
            return [{"file": "mod.py", "name": "a"}, {"file": "mod.py", "name": "b"}]
        return []  # no cross-file (Level-2) edges

    monkeypatch.setattr(code_graph, "_cgc_query", _fake_query)
    snap = await code_graph.extract_snapshot("/tmp/repo")
    assert snap["file_edges"] == []
    assert {"file": "mod.py", "name": "a"} in snap["functions"]
    assert {"source_file": "mod.py", "source": "a", "target_file": "mod.py", "target": "b"} in snap["function_calls"]


async def test_extract_snapshot_empty_when_no_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_query(_cypher: str) -> list[dict]:
        return []

    monkeypatch.setattr(code_graph, "_cgc_query", _fake_query)
    assert await code_graph.extract_snapshot("/tmp/repo") == {}


async def test_extract_snapshot_empty_repo_dir() -> None:
    assert await code_graph.extract_snapshot("") == {}


def test_module_leaf_handles_path_and_dotted_specifiers() -> None:
    assert code_graph._module_leaf("./galaxy-graph") == "galaxy-graph"  # TS relative
    assert code_graph._module_leaf("$lib/api/schemas") == "schemas"  # TS alias path
    assert code_graph._module_leaf("app.services.galaxy_query") == "galaxy_query"  # Python dotted
    assert code_graph._module_leaf("./bar.ts") == "bar"  # explicit extension stripped
    assert code_graph._module_leaf("force-graph") == "force-graph"  # bare npm pkg (leaf as-is)


def test_resolve_import_edges_unique_stem_match() -> None:
    files = ["api/app/services/galaxy_query.py", "api/app/main.py"]
    rows = [{"source": "api/app/main.py", "module": "app.services.galaxy_query"}]  # Python dotted
    assert code_graph._resolve_import_edges(rows, files, set()) == [
        {"source": "api/app/main.py", "target": "api/app/services/galaxy_query.py"}
    ]


def test_resolve_import_edges_drops_ambiguous_external_and_self() -> None:
    files = ["a/util.py", "b/util.py", "app/main.py"]
    rows = [
        {"source": "app/main.py", "module": "./util"},  # ambiguous (two util.py) → dropped
        {"source": "app/main.py", "module": "os"},  # external (no repo file) → dropped
        {"source": "app/main.py", "module": "./main"},  # resolves to itself → dropped
    ]
    assert code_graph._resolve_import_edges(rows, files, set()) == []


def test_resolve_import_edges_dedups_against_seen() -> None:
    files = ["x.ts", "bar.ts"]
    seen = {("x.ts", "bar.ts")}  # already added by CALLS
    rows = [{"source": "x.ts", "module": "./bar"}]
    assert code_graph._resolve_import_edges(rows, files, seen) == []


# --- merge_snapshots (issue 250): CGC preferred, deterministic fallback fills gaps ---------------
_CGC = {
    "file_edges": [{"source": "a.py", "target": "b.py"}],
    "functions": [{"file": "a.py", "name": "cgc_fn"}],
    "function_calls": [{"source_file": "a.py", "source": "cgc_fn", "target_file": "b.py", "target": "cgc_fn2"}],
}
_DET = {
    "file_edges": [{"source": "c.py", "target": "d.py"}],
    "functions": [{"file": "c.py", "name": "det_fn"}],
    "function_calls": [{"source_file": "c.py", "source": "det_fn", "target_file": "c.py", "target": "det_fn2"}],
}


def test_merge_prefers_cgc_when_present() -> None:
    assert code_graph.merge_snapshots(_CGC, _DET) == _CGC


def test_merge_fills_l3_from_deterministic_when_cgc_empty() -> None:
    # CGC indexed but found no functions (e.g. unsupported language) → L3 comes from deterministic,
    # as a pair (functions + function_calls from the same source for name consistency).
    merged = code_graph.merge_snapshots({"file_edges": _CGC["file_edges"], "functions": [], "function_calls": []}, _DET)
    assert merged["file_edges"] == _CGC["file_edges"]  # CGC file_edges kept (non-empty)
    assert merged["functions"] == _DET["functions"]
    assert merged["function_calls"] == _DET["function_calls"]


def test_merge_uses_deterministic_when_cgc_absent() -> None:
    assert code_graph.merge_snapshots({}, _DET) == _DET


def test_merge_empty_when_both_empty() -> None:
    assert code_graph.merge_snapshots({}, {}) == {}
