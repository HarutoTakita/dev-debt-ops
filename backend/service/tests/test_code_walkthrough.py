"""Unit tests for code-walkthrough generation (issue 217 PR2).

Covers the shared ``clean_steps`` re-anchoring, the walkthrough agent's ``save_walkthrough`` capture
+ tool wiring, and ``build_walkthrough_agentic``'s agentic-then-fallback behaviour. The ADK agent is
never driven (``_run_walkthrough_agent`` is patched), mirroring the stack-analysis test approach.
"""

from types import SimpleNamespace

import pytest

from service.agents import serena_mcp
from service.agents.budget import RunBudget
from service.agents.serena_mcp import build_serena_toolset
from service.services import code_walkthrough
from service.services.code_walkthrough import build_walkthrough_agent, build_walkthrough_agentic, clean_steps

# --- clean_steps -----------------------------------------------------------


def test_clean_steps_reanchors_start_line_to_matching_text() -> None:
    """start_line is snapped to the file line whose text matches start_text; end_line shifts equally."""
    lines = ["def a():", "    pass", "", "def target():", "    return 1"]
    raw = [{"start_line": 1, "end_line": 2, "start_text": "def target():", "title": "t", "explanation": "x"}]
    steps = clean_steps(raw, lines)
    assert steps == [{"start_line": 4, "end_line": 5, "title": "t", "explanation": "x"}]


def test_clean_steps_drops_invalid_and_clamps() -> None:
    """Items without explanation/line numbers are dropped; ranges are clamped to the file length."""
    lines = ["a", "b", "c"]
    raw = [
        {"start_line": 1, "end_line": 99, "title": "", "explanation": "keep"},  # end clamped to 3
        {"start_line": 2, "end_line": 2, "explanation": ""},  # dropped (no explanation)
        {"title": "no lines", "explanation": "drop"},  # dropped (no line numbers)
    ]
    steps = clean_steps(raw, lines)
    assert steps == [{"start_line": 1, "end_line": 3, "title": "", "explanation": "keep"}]


# --- walkthrough agent -----------------------------------------------------


def test_build_walkthrough_agent_save_tool_captures_steps() -> None:
    """save_walkthrough records (only dict) steps into the caller's ``captured`` out-parameter."""
    captured: list[dict] = []
    agent = build_walkthrough_agent(path="app/main.py", budget=RunBudget(), captured=captured)
    save = next(t for t in agent.tools if getattr(t, "__name__", "") == "save_walkthrough")

    msg = save([{"start_line": 1, "end_line": 2, "explanation": "x"}, "not-a-dict"])

    assert captured == [{"start_line": 1, "end_line": 2, "explanation": "x"}]
    assert "saved 1" in msg


def test_build_walkthrough_agent_appends_serena_toolset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a Serena toolset the agent gets save_walkthrough + the toolset; without it, just save."""
    # build_serena_toolset は serena バイナリ非存在時に None を返す（graceful, issue 059c）。バイナリ有りを
    # 装って McpToolset を生成する（プロセスは connect まで起動しないので Serena 未インストールでも可）。
    monkeypatch.setattr(serena_mcp.shutil, "which", lambda _cmd: "/usr/bin/serena")
    toolset = build_serena_toolset("/tmp/does-not-matter")
    with_serena = build_walkthrough_agent(path="x", budget=RunBudget(), captured=[], serena_toolset=toolset)
    without = build_walkthrough_agent(path="x", budget=RunBudget(), captured=[])
    assert toolset in with_serena.tools
    assert len(with_serena.tools) == 2
    assert len(without.tools) == 1


# --- build_walkthrough_agentic (agentic + fallback) ------------------------


class _FakeClient:
    def __init__(self, content: str) -> None:
        self._content = content

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> SimpleNamespace:
        return SimpleNamespace(content=self._content)


async def test_build_walkthrough_agentic_uses_agent_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the agent saves steps, they are cleaned and returned without the direct fallback."""

    async def fake_agent(owner, repo, path, ref, content, token):
        return [{"start_line": 1, "end_line": 1, "start_text": "x = 1", "title": "t", "explanation": "e"}]

    called = {"direct": False}

    async def fake_direct(path, content):
        called["direct"] = True
        return []

    monkeypatch.setattr(code_walkthrough, "_run_walkthrough_agent", fake_agent)
    monkeypatch.setattr(code_walkthrough.gemini_stack_service, "generate_code_walkthrough", fake_direct)

    steps = await build_walkthrough_agentic(_FakeClient("x = 1\ny = 2"), "o", "r", "f.py", "main", token="t")  # ty: ignore[invalid-argument-type]

    assert steps == [{"start_line": 1, "end_line": 1, "title": "t", "explanation": "e"}]
    assert called["direct"] is False


async def test_build_walkthrough_agentic_falls_back_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty agent result falls back to the direct Gemini walkthrough."""

    async def empty_agent(owner, repo, path, ref, content, token):
        return []

    async def fake_direct(path, content):
        return [{"start_line": 2, "end_line": 2, "start_text": "y = 2", "title": "d", "explanation": "de"}]

    monkeypatch.setattr(code_walkthrough, "_run_walkthrough_agent", empty_agent)
    monkeypatch.setattr(code_walkthrough.gemini_stack_service, "generate_code_walkthrough", fake_direct)

    steps = await build_walkthrough_agentic(_FakeClient("x = 1\ny = 2"), "o", "r", "f.py", "main", token="t")  # ty: ignore[invalid-argument-type]

    assert steps == [{"start_line": 2, "end_line": 2, "title": "d", "explanation": "de"}]


async def test_build_walkthrough_agentic_falls_back_when_agent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An agent/runtime exception is swallowed and the direct path is used."""

    async def boom_agent(owner, repo, path, ref, content, token):
        raise RuntimeError("serena exploded")

    async def fake_direct(path, content):
        return [{"start_line": 1, "end_line": 1, "start_text": "x = 1", "title": "d", "explanation": "de"}]

    monkeypatch.setattr(code_walkthrough, "_run_walkthrough_agent", boom_agent)
    monkeypatch.setattr(code_walkthrough.gemini_stack_service, "generate_code_walkthrough", fake_direct)

    steps = await build_walkthrough_agentic(_FakeClient("x = 1"), "o", "r", "f.py", "main", token="t")  # ty: ignore[invalid-argument-type]

    assert steps == [{"start_line": 1, "end_line": 1, "title": "d", "explanation": "de"}]


async def test_build_walkthrough_agentic_empty_content_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A file with no content returns [] without invoking the agent or the direct path."""
    steps = await build_walkthrough_agentic(_FakeClient(""), "o", "r", "f.py", "main", token="t")  # ty: ignore[invalid-argument-type]
    assert steps == []
