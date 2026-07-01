"""Agentic learning-plan authoring (issue 263): capture + graceful fallback."""

import pytest

from service.agents.budget import RunBudget
from service.agents.learning_agent import build_external_resources_agent, build_learning_steps_agent
from service.services import gemini_stack_service, learning_authoring


def test_learning_agents_save_tools_capture() -> None:
    """Each learning agent's save tool records its output into ``captured``."""
    cap_steps: dict = {}
    steps_agent = build_learning_steps_agent(budget=RunBudget(), captured=cap_steps)
    (save_steps,) = [t for t in steps_agent.tools if getattr(t, "__name__", "") == "save_learning_steps"]
    save_steps([{"source_ref": "a.py", "title": "t", "summary": "s"}])
    assert cap_steps["steps"][0]["source_ref"] == "a.py"

    cap_res: dict = {}
    res_agent = build_external_resources_agent(budget=RunBudget(), captured=cap_res)
    (save_res,) = [t for t in res_agent.tools if getattr(t, "__name__", "") == "save_resources"]
    save_res([{"name": "React", "title": "Docs", "url": "https://x"}])
    assert cap_res["resources"][0]["name"] == "React"


async def test_code_steps_agentic_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_run(**_kwargs: object) -> list[str]:
        return []

    async def _fake_direct(name: str, desc: str, files: list[str]) -> list[dict]:
        return [{"source_ref": files[0], "title": "fallback"}]

    monkeypatch.setattr(learning_authoring, "run_single_agent", _noop_run)
    monkeypatch.setattr(gemini_stack_service, "generate_code_learning_steps", _fake_direct)
    out = await learning_authoring.generate_code_learning_steps_agentic("F", "", ["a.py"], owner="o", repo="r")
    assert out[0]["title"] == "fallback"


async def test_external_resources_agentic_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_run(**_kwargs: object) -> list[str]:
        return []

    async def _fake_direct(concepts: list[str]) -> list[dict]:
        return [{"name": concepts[0], "title": "fallback", "url": "https://x"}]

    monkeypatch.setattr(learning_authoring, "run_single_agent", _noop_run)
    monkeypatch.setattr(gemini_stack_service, "generate_external_resources", _fake_direct)
    out = await learning_authoring.generate_external_resources_agentic(["caching"], owner="o", repo="r")
    assert out[0]["title"] == "fallback"


async def test_agentic_empty_inputs_are_noops() -> None:
    assert await learning_authoring.generate_code_learning_steps_agentic("F", "", [], owner="o", repo="r") == []
    assert await learning_authoring.generate_external_resources_agentic([], owner="o", repo="r") == []
