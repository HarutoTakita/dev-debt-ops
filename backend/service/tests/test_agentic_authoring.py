"""Unit tests for agentic refactor + quiz authoring (issue 217 PR3).

Covers the agents' save-tool capture / tool wiring and the ``*_agentic`` services'
agentic-then-fallback behaviour. The ADK agent is never driven (``_run_*_agent`` is patched),
mirroring the stack-analysis / walkthrough test approach.
"""

import pytest

from service.agents.budget import RunBudget
from service.agents.quiz_agent import build_quiz_agent
from service.agents.refactor_agent import build_refactor_agent
from service.agents.serena_mcp import build_serena_toolset
from service.services import quiz_authoring, repayment_refactor

# --- agents: save-tool capture + wiring ------------------------------------


def test_refactor_agent_save_tool_captures_proposal() -> None:
    """save_refactor records ``{new_content, pr_title, pr_body}`` into the caller's ``captured``."""
    captured: dict = {}
    agent = build_refactor_agent(path="a.py", notes="dup", budget=RunBudget(), captured=captured)
    save = next(t for t in agent.tools if getattr(t, "__name__", "") == "save_refactor")
    save("new code", "title", "body")
    assert captured == {"new_content": "new code", "pr_title": "title", "pr_body": "body"}


def test_quiz_agent_save_tool_captures_and_filters() -> None:
    """save_quiz keeps only dict questions and a dict answer_key in ``captured``."""
    captured: dict = {}
    agent = build_quiz_agent(label="feat", budget=RunBudget(), captured=captured)
    save = next(t for t in agent.tools if getattr(t, "__name__", "") == "save_quiz")
    msg = save([{"id": "q1"}, "bad"], {"q1": {"answer": "a"}})
    assert captured["questions"] == [{"id": "q1"}]
    assert captured["answer_key"] == {"q1": {"answer": "a"}}
    assert "saved 1" in msg


def test_agents_append_serena_toolset() -> None:
    """Each agent gets its save tool plus the Serena toolset when one is provided."""
    toolset = build_serena_toolset("/tmp/x")
    refactor = build_refactor_agent(path="a.py", notes="", budget=RunBudget(), captured={}, serena_toolset=toolset)
    quiz = build_quiz_agent(label="f", budget=RunBudget(), captured={}, serena_toolset=toolset)
    assert toolset in refactor.tools
    assert toolset in quiz.tools


# --- generate_refactor_agentic --------------------------------------------

_ORIGINAL = "def f():\n    pass\n"


async def test_refactor_agentic_uses_plausible_agent_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plausible agent proposal is returned without the direct fallback."""

    async def fake_agent(*args: object, **kwargs: object) -> dict:
        return {"new_content": "def f():\n    return 1\n", "pr_title": "T", "pr_body": "B"}

    called = {"direct": False}

    async def fake_direct(path: str, content: str, notes: str) -> dict:
        called["direct"] = True
        return {"new_content": content, "pr_title": "x", "pr_body": "y"}

    monkeypatch.setattr(repayment_refactor, "_run_refactor_agent", fake_agent)
    monkeypatch.setattr(repayment_refactor.gemini_stack_service, "generate_refactor", fake_direct)

    out = await repayment_refactor.generate_refactor_agentic("o", "r", "main", "a.py", _ORIGINAL, "dup", token="t")
    assert out == {"new_content": "def f():\n    return 1\n", "pr_title": "T", "pr_body": "B"}
    assert called["direct"] is False


async def test_refactor_agentic_falls_back_on_implausible(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty/implausible agent proposal falls back to the direct refactor."""

    async def fake_agent(*args: object, **kwargs: object) -> dict:
        return {"new_content": "", "pr_title": "T", "pr_body": "B"}  # implausible (empty)

    async def fake_direct(path: str, content: str, notes: str) -> dict:
        return {"new_content": "def f():\n    return 2\n", "pr_title": "D", "pr_body": "DB"}

    monkeypatch.setattr(repayment_refactor, "_run_refactor_agent", fake_agent)
    monkeypatch.setattr(repayment_refactor.gemini_stack_service, "generate_refactor", fake_direct)

    out = await repayment_refactor.generate_refactor_agentic("o", "r", "main", "a.py", _ORIGINAL, "dup", token="t")
    assert out["new_content"] == "def f():\n    return 2\n"


async def test_refactor_agentic_falls_back_when_agent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An agent/runtime exception is swallowed and the direct refactor is used."""

    async def boom(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("serena exploded")

    async def fake_direct(path: str, content: str, notes: str) -> dict:
        return {"new_content": "def f():\n    return 3\n", "pr_title": "D", "pr_body": "DB"}

    monkeypatch.setattr(repayment_refactor, "_run_refactor_agent", boom)
    monkeypatch.setattr(repayment_refactor.gemini_stack_service, "generate_refactor", fake_direct)

    out = await repayment_refactor.generate_refactor_agentic("o", "r", "main", "a.py", _ORIGINAL, "dup", token="t")
    assert out["new_content"] == "def f():\n    return 3\n"


# --- generate_quiz_agentic -------------------------------------------------


async def test_quiz_agentic_uses_agent_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the agent saves questions they are returned without the direct fallback."""

    async def fake_agent(*args: object, **kwargs: object) -> dict:
        return {"questions": [{"id": "q1"}], "answer_key": {"q1": {"answer": "a"}}}

    called = {"direct": False}

    async def fake_direct(label: str, content: str) -> dict:
        called["direct"] = True
        return {"questions": [], "answer_key": {}}

    monkeypatch.setattr(quiz_authoring, "_run_quiz_agent", fake_agent)
    monkeypatch.setattr(quiz_authoring.gemini_stack_service, "generate_quiz", fake_direct)

    out = await quiz_authoring.generate_quiz_agentic("o", "r", "main", "feat", "code", token="t")
    assert out == {"questions": [{"id": "q1"}], "answer_key": {"q1": {"answer": "a"}}}
    assert called["direct"] is False


async def test_quiz_agentic_falls_back_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty agent result falls back to the direct quiz generation."""

    async def empty_agent(*args: object, **kwargs: object) -> dict:
        return {}

    async def fake_direct(label: str, content: str) -> dict:
        return {"questions": [{"id": "d1"}], "answer_key": {}}

    monkeypatch.setattr(quiz_authoring, "_run_quiz_agent", empty_agent)
    monkeypatch.setattr(quiz_authoring.gemini_stack_service, "generate_quiz", fake_direct)

    out = await quiz_authoring.generate_quiz_agentic("o", "r", "main", "feat", "code", token="t")
    assert out["questions"] == [{"id": "d1"}]
