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
        if "CONTAINS]->(a:Function)-[:CALLS]" in cypher:  # intra-file function calls (Level-3 edges)
            return [{"file": "mod.py", "source": "a", "target": "b"}]
        if "CONTAINS]->(fn:Function)" in cypher:  # per-file functions (Level-3 nodes)
            return [{"file": "mod.py", "name": "a"}, {"file": "mod.py", "name": "b"}]
        return [{"source": "app.py", "target": "mod.py"}]  # file↔file (Level-2 edges)

    monkeypatch.setattr(code_graph, "_cgc_query", _fake_query)
    snap = await code_graph.extract_snapshot("/tmp/repo")
    assert snap["file_edges"] == [{"source": "app.py", "target": "mod.py"}]
    assert {"file": "mod.py", "name": "a"} in snap["functions"]
    assert {"file": "mod.py", "source": "a", "target": "b"} in snap["function_calls"]


async def test_extract_snapshot_empty_when_no_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_query(_cypher: str) -> list[dict]:
        return []

    monkeypatch.setattr(code_graph, "_cgc_query", _fake_query)
    assert await code_graph.extract_snapshot("/tmp/repo") == {}


async def test_extract_snapshot_empty_repo_dir() -> None:
    assert await code_graph.extract_snapshot("") == {}
