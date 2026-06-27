"""agentic-analysis pipeline + Twin Agent graph tests (issue 069).

The ADK ``Runner`` is never driven (no live Vertex AI) — ``run_twin_agent`` is patched, mirroring
``test_stack_analysis``. Construction / tool / plugin logic is exercised directly; ``process`` is
tested with GitHub + the agent run mocked.
"""

from unittest.mock import AsyncMock

import pytest
from google.adk.agents import LoopAgent
from google.adk.planners import PlanReActPlanner

from service.agents.budget import RunBudget
from service.agents.plugin import TraceRecorderPlugin
from service.agents.remediation import build_remediation_tools
from service.agents.tools import build_repo_tools
from service.agents.twin import build_twin_loop
from service.pipelines import (
    agentic_analysis,
    code_debt_detection,
    feature_clustering,
    kc_analysis,
    knowledge_debt_detection,
)
from service.services.github_git_client import FileContent, TreeItem
from shared.enums import JobType, ResultStatus
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest
from shared.schemas.stack_analysis import GitHubRef


def _request() -> AgenticAnalysisRequest:
    return AgenticAnalysisRequest(
        job_id="job-1",
        job_type=JobType.AGENTIC_ANALYSIS,
        owner="acme",
        repo="rosetta",
        project_id="proj-1",
        github=GitHubRef(installation_id=123),
        requested_by="user-1",
    )


# --- Twin Agent graph construction (no network) ----------------------------


class TestTwinConstruction:
    def test_build_twin_loop_shape(self) -> None:
        """LoopAgent wraps the coordinator; the coordinator delegates to 3 specialists + exit_loop."""
        loop = build_twin_loop(client=AsyncMock(), budget=RunBudget(), recommendations=[], max_iterations=2)
        assert isinstance(loop, LoopAgent)
        assert loop.max_iterations == 2
        assert len(loop.sub_agents) == 1

        coordinator = loop.sub_agents[0]
        assert coordinator.name == "twin_agent"
        assert isinstance(coordinator.planner, PlanReActPlanner)
        tool_names = [getattr(tool, "name", getattr(tool, "__name__", "?")) for tool in coordinator.tools]
        assert "knowledge_debt_agent" in tool_names
        assert "code_debt_agent" in tool_names
        assert "remediation_strategist" in tool_names
        assert "exit_loop" in tool_names

    def test_recommend_remediation_records(self) -> None:
        """The remediation tool records structured recommendations and normalises the action."""
        recommendations: list[dict[str, str]] = []
        (recommend_remediation,) = build_remediation_tools(recommendations)
        recommend_remediation(target="auth/login.py", debt_kind="knowledge", action="quiz", rationale="属人化")
        recommend_remediation(target="x.py", debt_kind="code", action="bogus", rationale="r")
        assert recommendations[0]["action"] == "quiz"
        assert recommendations[0]["target"] == "auth/login.py"
        assert recommendations[1]["action"] == "other"


# --- repo tools (GitHub client mocked) -------------------------------------


class TestRepoTools:
    async def test_list_repo_source_files_filters_tree(self) -> None:
        client = AsyncMock()
        client.get_repository_tree.return_value = [
            TreeItem(path="app/main.py", type="blob", size=100),
            TreeItem(path="node_modules/x/index.js", type="blob", size=50),
            TreeItem(path="src", type="tree", size=None),
        ]
        list_repo_source_files, _read, _assess = build_repo_tools(client, RunBudget())
        result = await list_repo_source_files("acme", "rosetta", "main")
        assert "app/main.py" in result
        assert "node_modules/x/index.js" not in result

    async def test_read_file_truncates_and_charges_budget(self) -> None:
        client = AsyncMock()
        client.get_file_content.return_value = FileContent(path="big.py", content="x" * 10_000, sha="s", size=10_000)
        budget = RunBudget()
        _list, read_file, _assess = build_repo_tools(client, budget)
        result = await read_file("acme", "rosetta", "big.py")
        assert "(truncated)" in result
        assert budget.files_read == 1


# --- plugin ----------------------------------------------------------------


class _FakePart:
    def __init__(self, text: str) -> None:
        self.function_call = None
        self.function_response = None
        self.text = text


class _FakeContent:
    def __init__(self, parts: list[object]) -> None:
        self.parts = parts


class _FakeEvent:
    def __init__(self, text: str) -> None:
        self.content = _FakeContent([_FakePart(text)])


class TestPlugin:
    async def test_on_event_records_trace(self) -> None:
        plugin = TraceRecorderPlugin()
        await plugin.on_event_callback(invocation_context=object(), event=_FakeEvent("done"))
        assert plugin.trace == ["[summary] done"]


# --- process (GitHub + agent run mocked) -----------------------------------


class TestProcess:
    async def test_process_runs_backbone_then_agent(self, mocker) -> None:
        # Deterministic backbone pipelines are mocked (they upsert tables in real runs); assert
        # each is invoked and that the agent judgement layer's trace/recommendations follow.
        for module in (feature_clustering, code_debt_detection, kc_analysis, knowledge_debt_detection):
            mocker.patch.object(module, "process", AsyncMock())
        mocker.patch.object(agentic_analysis, "_mint_installation_token", AsyncMock(return_value="tok"))
        mocker.patch.object(agentic_analysis, "GitHubGitClient", return_value=AsyncMock())
        recs = [{"target": "auth.py", "debt_kind": "knowledge", "action": "quiz", "rationale": "属人化"}]
        mocker.patch.object(
            agentic_analysis,
            "run_twin_agent",
            AsyncMock(return_value=(["[summary] 危険な機能を特定"], recs)),
        )

        ctx = PipelineContext(session=AsyncMock())
        result = await agentic_analysis.process(_request(), ctx)

        assert result.status == ResultStatus.COMPLETED
        assert result.job_type == JobType.AGENTIC_ANALYSIS
        assert feature_clustering.process.await_count == 1
        assert knowledge_debt_detection.process.await_count == 1
        assert result.agent_trace == [
            "[backbone] feature_clustering done",
            "[backbone] code_debt_detection done",
            "[backbone] kc_analysis done",
            "[backbone] knowledge_debt_detection done",
            "[summary] 危険な機能を特定",
        ]
        assert result.summary == "[summary] 危険な機能を特定"
        assert result.recommendations == recs

    async def test_process_requires_session(self) -> None:
        with pytest.raises(RuntimeError, match="requires a DB session"):
            await agentic_analysis.process(_request(), PipelineContext(session=None))
