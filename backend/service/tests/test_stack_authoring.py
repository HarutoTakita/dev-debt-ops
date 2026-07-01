"""Agentic tech-stack authoring (issue 263): capture + graceful fallback."""

import pytest

from service.agents.budget import RunBudget
from service.agents.stack_agent import build_stack_agent
from service.services import gemini_stack_service, stack_authoring


def test_stack_agent_save_tool_captures() -> None:
    """The agent's save_stack tool records the classification into ``captured``."""
    captured: dict = {}
    agent = build_stack_agent(budget=RunBudget(), captured=captured)
    (save_stack,) = [t for t in agent.tools if getattr(t, "__name__", "") == "save_stack"]
    save_stack({"languages": [{"name": "Python", "confidence": "high"}], "categories": {}})
    assert captured["stack"]["languages"][0]["name"] == "Python"


async def test_classify_stack_agentic_falls_back_when_agent_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the agent saves nothing (or errors), fall back to the direct Gemini classification."""

    async def _noop_run(**_kwargs: object) -> list[str]:
        return []

    async def _fake_direct(files: dict[str, str]) -> dict:
        return {"languages": [{"name": "Go", "confidence": "high"}], "categories": {}}

    monkeypatch.setattr(stack_authoring, "run_single_agent", _noop_run)
    monkeypatch.setattr(gemini_stack_service, "analyze_tech_stack", _fake_direct)
    out = await stack_authoring.classify_stack_agentic({"go.mod": "module x"}, owner="o", repo="r")
    assert out["languages"][0]["name"] == "Go"
