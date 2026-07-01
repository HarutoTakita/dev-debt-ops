"""agentic-analysis pipeline + Twin Agent graph tests (issue 069 → 266).

The ADK ``Runner`` is never driven (no live Vertex AI) — ``run_analysis_agent`` / ``run_twin_agent``
are patched, mirroring ``test_stack_analysis``. Construction / tool / plugin logic is exercised
directly; ``process`` is tested with GitHub + the agent run mocked.
"""

from unittest.mock import AsyncMock

import pytest
from google.adk.agents import SequentialAgent

from service.agents.budget import RunBudget
from service.agents.plugin import TraceRecorderPlugin
from service.agents.remediation import build_remediation_tools
from service.agents.tools import build_repo_tools
from service.agents.twin import build_twin_loop
from service.pipelines import (
    agentic_analysis,
    baseline_generation,
    code_debt_detection,
    feature_clustering,
    kc_analysis,
    knowledge_debt_detection,
    stack_analysis,
)
from service.services.github_git_client import FileContent, TreeItem
from shared.enums import JobType, ResultStatus
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest
from shared.schemas.base_analysis import BaseAnalysis, BaseFeature
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
        """Rule-based pipeline: a SequentialAgent runs knowledge → code → remediation in order."""
        loop = build_twin_loop(client=AsyncMock(), budget=RunBudget(), recommendations=[])
        assert isinstance(loop, SequentialAgent)
        names = [a.name for a in loop.sub_agents]
        assert names == ["knowledge_debt_agent", "code_debt_agent", "remediation_strategist"]

    def test_specialists_get_serena_toolset(self) -> None:
        """The Serena (LSP) toolset is attached to BOTH detection specialists when provided."""
        from service.agents.serena_mcp import build_serena_toolset

        toolset = build_serena_toolset("/tmp/repo")  # construction is lazy; no subprocess spawned
        loop = build_twin_loop(client=AsyncMock(), budget=RunBudget(), recommendations=[], serena_toolset=toolset)
        by_name = {a.name: a for a in loop.sub_agents}
        assert toolset in by_name["code_debt_agent"].tools
        assert toolset in by_name["knowledge_debt_agent"].tools

    def test_specialists_get_github_and_trivy_toolsets(self) -> None:
        """MCP is stage-scoped: GitHub MCP → knowledge only; Trivy MCP → code only (+ clone path)."""
        from service.agents.github_mcp import build_github_toolset
        from service.agents.trivy_mcp import build_trivy_toolset

        gh = build_github_toolset("tok")
        tv = build_trivy_toolset()
        loop = build_twin_loop(
            client=AsyncMock(),
            budget=RunBudget(),
            recommendations=[],
            github_toolset=gh,
            trivy_toolset=tv,
            repo_dir="/tmp/clone-xyz",
        )
        by_name = {a.name: a for a in loop.sub_agents}
        code = by_name["code_debt_agent"]
        know = by_name["knowledge_debt_agent"]
        assert gh in know.tools  # GitHub → knowledge (process/history = knowledge-debt signal)
        assert gh not in code.tools  # GitHub NOT on code
        assert tv in code.tools  # Trivy → code (SCA/secret/misconfig = code-debt signal)
        assert tv not in know.tools  # Trivy NOT on knowledge
        assert "/tmp/clone-xyz" in code.instruction  # path injected for scan_filesystem

    def test_code_specialist_gets_semgrep_toolset(self) -> None:
        """Semgrep MCP → code specialist only (real static analysis = code-debt signal), issue 204."""
        from service.agents.semgrep_mcp import build_semgrep_toolset

        sg = build_semgrep_toolset()  # construction is lazy; no subprocess spawned
        loop = build_twin_loop(client=AsyncMock(), budget=RunBudget(), recommendations=[], semgrep_toolset=sg)
        by_name = {a.name: a for a in loop.sub_agents}
        assert sg in by_name["code_debt_agent"].tools  # Semgrep → code
        assert sg not in by_name["knowledge_debt_agent"].tools  # NOT on knowledge

    def test_specialists_get_code_graph_toolset(self) -> None:
        """CodeGraphContext (マクロ) → BOTH specialists; repo path is injected into the hint (issue 235)."""
        from service.agents.code_graph_mcp import build_code_graph_toolset

        cg = build_code_graph_toolset()  # construction is lazy; no subprocess spawned
        loop = build_twin_loop(
            client=AsyncMock(),
            budget=RunBudget(),
            recommendations=[],
            code_graph_toolset=cg,
            repo_dir="/tmp/clone-xyz",
        )
        by_name = {a.name: a for a in loop.sub_agents}
        assert cg in by_name["code_debt_agent"].tools
        assert cg in by_name["knowledge_debt_agent"].tools
        assert "/tmp/clone-xyz" in by_name["code_debt_agent"].instruction  # repo_path injected into _CGC_HINT

    def test_recommend_remediation_records(self) -> None:
        """The remediation tool records structured recommendations and normalises the action."""
        recommendations: list[dict[str, str]] = []
        (recommend_remediation,) = build_remediation_tools(recommendations)
        recommend_remediation(target="auth/login.py", debt_kind="knowledge", action="quiz", rationale="属人化")
        recommend_remediation(target="x.py", debt_kind="code", action="bogus", rationale="r")
        assert recommendations[0]["action"] == "quiz"
        assert recommendations[0]["target"] == "auth/login.py"
        assert recommendations[1]["action"] == "other"


class TestRunnerMcpLifecycle:
    async def test_all_mcp_toolsets_closed_after_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_twin_agent builds Serena+Trivy+Semgrep+CodeGraph (repo_dir) + GitHub (token) and closes them all."""
        from service.agents import runner

        closed = {"n": 0}

        class _FakeToolset:
            async def close(self) -> None:
                closed["n"] += 1

        class _FakeRunner:
            def __init__(self, **_kwargs: object) -> None:
                pass

            async def run_async(self, **_kwargs: object):
                return
                yield  # unreachable — makes this an async generator

        monkeypatch.setattr(runner, "build_serena_toolset", lambda _dir: _FakeToolset())
        monkeypatch.setattr(runner, "build_trivy_toolset", lambda: _FakeToolset())
        monkeypatch.setattr(runner, "build_semgrep_toolset", lambda: _FakeToolset())
        monkeypatch.setattr(runner, "build_code_graph_toolset", lambda: _FakeToolset())
        monkeypatch.setattr(runner, "build_github_toolset", lambda _tok: _FakeToolset())
        monkeypatch.setattr(runner, "build_twin_loop", lambda **_kwargs: object())
        monkeypatch.setattr(runner, "Runner", _FakeRunner)

        trace, recs = await runner.run_twin_agent(
            client=AsyncMock(),
            owner="acme",
            repo="rosetta",
            branch="main",
            budget=RunBudget(),
            repo_dir="/tmp/x",
            github_token="tok",
        )
        assert closed["n"] == 5  # serena + trivy + semgrep + code_graph + github all closed
        assert trace == []
        assert recs == []

    async def test_analysis_agent_closes_exploration_toolsets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_analysis_agent builds only the exploration MCP (Serena + CodeGraph on repo_dir, GitHub on
        token) — NOT Trivy/Semgrep (those run as deterministic blocks) — and closes them all."""
        from service.agents import runner

        closed = {"n": 0}

        class _FakeToolset:
            async def close(self) -> None:
                closed["n"] += 1

        class _FakeRunner:
            def __init__(self, **_kwargs: object) -> None:
                pass

            async def run_async(self, **_kwargs: object):
                return
                yield  # unreachable — makes this an async generator

        monkeypatch.setattr(runner, "build_serena_toolset", lambda _dir: _FakeToolset())
        monkeypatch.setattr(runner, "build_code_graph_toolset", lambda: _FakeToolset())
        monkeypatch.setattr(runner, "build_github_toolset", lambda _tok: _FakeToolset())
        monkeypatch.setattr(runner, "build_analysis_agent", lambda **_kwargs: object())
        monkeypatch.setattr(runner, "Runner", _FakeRunner)

        trace, base = await runner.run_analysis_agent(
            client=AsyncMock(),
            owner="acme",
            repo="rosetta",
            branch="main",
            budget=RunBudget(),
            repo_dir="/tmp/x",
            github_token="tok",
        )
        assert closed["n"] == 3  # serena + code_graph + github (no trivy/semgrep)
        assert trace == []
        assert base.is_empty()  # no save_base_analysis was called → empty base


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
    def _mock_backbone(self, mocker) -> None:
        """Mock every deterministic backbone step + GitHub token/client + clone (return None)."""
        for module in (feature_clustering, code_debt_detection, kc_analysis, knowledge_debt_detection):
            mocker.patch.object(module, "process", AsyncMock())
        mocker.patch.object(stack_analysis, "populate_tech_stack", AsyncMock())
        mocker.patch.object(
            baseline_generation,
            "generate_learning_and_quizzes",
            AsyncMock(return_value=["[generate] learning plan: auth", "[generate] quiz: auth"]),
        )
        mocker.patch.object(agentic_analysis, "_mint_installation_token", AsyncMock(return_value="tok"))
        mocker.patch.object(agentic_analysis, "GitHubGitClient", return_value=AsyncMock())
        mocker.patch.object(agentic_analysis.repo_checkout, "shallow_clone", AsyncMock(return_value=None))

    async def test_process_runs_agent_first_then_backbone(self, mocker) -> None:
        # Agent-first (issue 266): the Base Analysis Agent runs FIRST, then the deterministic backbone
        # (mocked) still produces the screen tables. Assert order and that a non-empty base is persisted.
        self._mock_backbone(mocker)
        base = BaseAnalysis(features=[BaseFeature(key="auth", name="Auth")], summary="s")
        mocker.patch.object(
            agentic_analysis,
            "run_analysis_agent",
            AsyncMock(return_value=(["[summary] 危険な機能を特定"], base)),
        )
        persist_base = mocker.patch.object(agentic_analysis, "_persist_base_analysis", AsyncMock())

        ctx = PipelineContext(session=AsyncMock())
        result = await agentic_analysis.process(_request(), ctx)

        assert result.status == ResultStatus.COMPLETED
        assert result.job_type == JobType.AGENTIC_ANALYSIS
        assert ctx.github_client is None  # 取得共通化: 共有クライアントは finally で必ず解放される
        assert feature_clustering.process.await_count == 1
        assert knowledge_debt_detection.process.await_count == 1
        assert baseline_generation.generate_learning_and_quizzes.await_count == 1
        persist_base.assert_awaited_once()  # non-empty base analysis persisted
        # agent-first (issue 268): the base features flow into the feature-clustering block as `clusters`.
        fc_clusters = feature_clustering.process.call_args.kwargs["clusters"]
        assert fc_clusters is not None
        assert fc_clusters[0]["key"] == "auth"
        assert result.agent_trace == [
            "[summary] 危険な機能を特定",  # agent-first: the agent trace precedes the backbone steps
            "[backbone] feature_clustering done",
            "[backbone] code_debt_detection done",
            "[backbone] kc_analysis done",
            "[backbone] knowledge_debt_detection done",
            "[backbone] stack_analysis done",
            "[generate] learning plan: auth",
            "[generate] quiz: auth",
        ]
        assert result.summary == "[summary] 危険な機能を特定"
        assert result.recommendations == []  # 判断レイヤ廃止に向け空

    async def test_empty_base_analysis_not_persisted(self, mocker) -> None:
        """An empty base analysis (agent produced nothing) is NOT persisted; backbone still runs."""
        self._mock_backbone(mocker)
        mocker.patch.object(agentic_analysis, "run_analysis_agent", AsyncMock(return_value=([], BaseAnalysis())))
        persist_base = mocker.patch.object(agentic_analysis, "_persist_base_analysis", AsyncMock())

        result = await agentic_analysis.process(_request(), PipelineContext(session=AsyncMock()))

        assert result.status == ResultStatus.COMPLETED
        persist_base.assert_not_awaited()
        assert feature_clustering.process.await_count == 1  # backbone still produces the screen tables
        # empty base → feature-clustering falls back to the deterministic model path (clusters=None).
        assert feature_clustering.process.call_args.kwargs["clusters"] is None

    async def test_agent_failure_still_completes(self, mocker) -> None:
        """issue 260/266: a base-agent failure (e.g. transient Gemini 502) must NOT fail/roll back the
        whole analysis — the deterministic backbone still runs and the job completes."""
        self._mock_backbone(mocker)
        mocker.patch.object(baseline_generation, "generate_learning_and_quizzes", AsyncMock(return_value=[]))
        mocker.patch.object(
            agentic_analysis, "run_analysis_agent", AsyncMock(side_effect=RuntimeError("502 Bad Gateway"))
        )

        result = await agentic_analysis.process(_request(), PipelineContext(session=AsyncMock()))

        assert result.status == ResultStatus.COMPLETED  # backbone preserved; job reaches a terminal state
        assert result.recommendations == []
        assert feature_clustering.process.await_count == 1  # backbone ran despite the agent failure
        assert any("[analysis_agent] failed" in s for s in result.agent_trace)

    async def test_persists_deterministic_snapshot_when_cgc_empty(self, mocker) -> None:
        """issue 250: when CGC indexes but returns an empty snapshot, the deterministic source-based
        snapshot (function_graph) fills L3 and is persisted, so the map shows for any repo."""
        self._mock_backbone(mocker)
        mocker.patch.object(baseline_generation, "generate_learning_and_quizzes", AsyncMock(return_value=[]))
        mocker.patch.object(agentic_analysis, "run_analysis_agent", AsyncMock(return_value=([], BaseAnalysis())))
        # clone + CGC build succeed, but CGC yields nothing → deterministic fallback fills L3.
        mocker.patch.object(agentic_analysis.repo_checkout, "shallow_clone", AsyncMock(return_value="/tmp/clone"))
        mocker.patch.object(agentic_analysis.code_graph, "build_graph", AsyncMock(return_value=True))
        mocker.patch.object(agentic_analysis.code_graph, "extract_snapshot", AsyncMock(return_value={}))
        det = {"file_edges": [], "functions": [{"file": "a.py", "name": "fn"}], "function_calls": []}
        mocker.patch.object(
            agentic_analysis.function_graph, "read_repo_sources", return_value={"a.py": "def fn(): ..."}
        )
        mocker.patch.object(agentic_analysis.function_graph, "build_snapshot", return_value=det)
        persist = mocker.patch.object(agentic_analysis, "_persist_code_graph", AsyncMock())

        result = await agentic_analysis.process(_request(), PipelineContext(session=AsyncMock()))

        assert result.status == ResultStatus.COMPLETED
        persist.assert_awaited_once()
        assert persist.await_args.args[2]["functions"] == det["functions"]  # deterministic L3 persisted

    async def test_process_requires_session(self) -> None:
        with pytest.raises(RuntimeError, match="requires a DB session"):
            await agentic_analysis.process(_request(), PipelineContext(session=None))
