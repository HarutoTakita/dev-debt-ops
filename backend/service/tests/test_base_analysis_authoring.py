"""Base Analysis Agent authoring tests (issue 266).

No live model: the two-stage agent is constructed directly and its ``save_base_analysis`` confirm
tool is called to verify it records into ``captured`` and that ``build_base_analysis`` assembles a
tolerant ``BaseAnalysis`` (bad items dropped, hard numbers absent).
"""

from typing import Any
from unittest.mock import AsyncMock

from google.adk.agents import SequentialAgent

from service.agents.base_analysis_tools import build_analysis_agent, build_base_analysis
from service.agents.budget import RunBudget


def _save_tool(agent: SequentialAgent):
    """Return the ``save_base_analysis`` tool from the author stage of the two-stage agent."""
    author = {a.name: a for a in agent.sub_agents}["base_author"]
    (tool,) = [t for t in author.tools if getattr(t, "__name__", "") == "save_base_analysis"]
    return tool


class TestBuildAnalysisAgent:
    def test_two_stage_shape(self) -> None:
        """The agent is a SequentialAgent: analysis_explorer → base_author."""
        agent = build_analysis_agent(client=AsyncMock(), budget=RunBudget(), captured={})
        assert isinstance(agent, SequentialAgent)
        assert [a.name for a in agent.sub_agents] == ["analysis_explorer", "base_author"]

    def test_explorer_gets_exploration_mcp_only(self) -> None:
        """Explorer gets Serena + GitHub + CodeGraph toolsets; the author only gets the save tool."""
        from service.agents.code_graph_mcp import build_code_graph_toolset
        from service.agents.github_mcp import build_github_toolset
        from service.agents.serena_mcp import build_serena_toolset

        serena = build_serena_toolset("/tmp/repo")  # construction is lazy; no subprocess spawned
        github = build_github_toolset("tok")
        cgc = build_code_graph_toolset()
        agent = build_analysis_agent(
            client=AsyncMock(),
            budget=RunBudget(),
            captured={},
            serena_toolset=serena,
            github_toolset=github,
            code_graph_toolset=cgc,
        )
        by_name = {a.name: a for a in agent.sub_agents}
        explorer_tools = by_name["analysis_explorer"].tools
        assert serena in explorer_tools
        assert github in explorer_tools
        assert cgc in explorer_tools
        # author has exactly one tool: save_base_analysis (no MCP / no exploration tools)
        assert [getattr(t, "__name__", "") for t in by_name["base_author"].tools] == ["save_base_analysis"]

    def test_save_tool_captures(self) -> None:
        """save_base_analysis records the agent output into ``captured`` (filtering malformed items)."""
        captured: dict[str, Any] = {}
        agent = build_analysis_agent(client=AsyncMock(), budget=RunBudget(), captured=captured)
        save = _save_tool(agent)
        save(
            features=[{"key": "auth", "name": "Auth"}, {"name": "no-key"}],  # 2nd dropped (no key)
            code_findings=[{"file_path": "a.py", "type": "complexity"}, {"type": "x"}],  # 2nd dropped (no path)
            knowledge_findings=[{"file_path": "b.py", "reason": "no_review"}],
            stack_terms=["Python", 123],  # non-str dropped
            summary="ok",
        )
        assert [f["key"] for f in captured["features"]] == ["auth"]
        assert [c["file_path"] for c in captured["code_findings"]] == ["a.py"]
        assert captured["knowledge_findings"][0]["file_path"] == "b.py"
        assert captured["stack_terms"] == ["Python"]
        assert captured["summary"] == "ok"


class TestBuildBaseAnalysis:
    def test_assembles_from_captured(self) -> None:
        captured = {
            "features": [{"key": "auth", "name": "Auth", "files": [{"path": "a.py", "confidence": 0.9}]}],
            "code_findings": [{"file_path": "a.py", "type": "complexity", "severity": "high"}],
            "knowledge_findings": [{"file_path": "b.py", "reason": "no_review"}],
            "stack_terms": ["Python"],
            "summary": "s",
        }
        base = build_base_analysis(captured)
        assert not base.is_empty()
        assert base.features[0].key == "auth"
        assert base.features[0].files[0].path == "a.py"
        assert base.code_findings[0].severity == "high"
        assert base.knowledge_findings[0].reason == "no_review"
        assert base.stack_terms == ["Python"]
        assert base.summary == "s"

    def test_tolerant_to_malformed_items(self) -> None:
        """A single malformed item is dropped, not fatal; empty captured → empty (fallback signal)."""
        captured = {"features": ["not-a-dict", {"key": "ok", "name": "Ok"}, {"missing": "key"}]}
        base = build_base_analysis(captured)
        assert [f.key for f in base.features] == ["ok"]  # only the valid dict survives
        assert build_base_analysis({}).is_empty()
