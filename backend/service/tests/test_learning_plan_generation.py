"""issue 035/068: learning-plan generation — code/stack sections + idempotency (GitHub/Gemini mocked)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import learning_plan_generation
from service.services.github_git_client import CommitInfo, TreeItem
from shared.enums import JobType
from shared.models import LearningPlan, LearningResource, LearningStep
from shared.pipelines.context import PipelineContext
from shared.schemas.learning_plan import LearningPlanGenerationRequest
from shared.schemas.stack_analysis import GitHubRef

_RECENT = (datetime.now(UTC) - timedelta(days=30)).isoformat()


class _FakeClient:
    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        return [
            TreeItem(path="docs/adr/0001-cache.md", type="blob", size=100),
            TreeItem(path="src/cache.py", type="blob", size=200),
            TreeItem(path="README.md", type="blob", size=50),
        ]

    async def list_commits(self, owner: str, repo: str, **kwargs: object) -> list[CommitInfo]:
        return [CommitInfo("sha", "alice", "a@x.com", 1, _RECENT, "m")]

    async def aclose(self) -> None:
        return None


def _patch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_code_steps(
        feature_name: str, feature_description: str, file_paths: list[str], *, owner: str = "", repo: str = ""
    ) -> list[dict]:
        # Section A: concept マッチで拾った 2 ファイルに説明つきステップを返す。
        return [
            {
                "source_ref": "docs/adr/0001-cache.md",
                "title": "ADR 0001",
                "summary": "キャッシュ方針の決定",
                "estimated_minutes": 15,
                "priority": "required",
            },
            {
                "source_ref": "src/cache.py",
                "title": "cache.py",
                "summary": "キャッシュ実装の要点",
                "estimated_minutes": 20,
                "priority": "required",
            },
        ]

    async def _fake_external(gap_concepts: list[str], *, owner: str = "", repo: str = "") -> list[dict]:
        # Section B: tech_stack 由来の一般リソース（mock は入力を無視）。
        return [
            {
                "kind": "docs",
                "title": "Caching docs",
                "url": "https://example.com/cache",
                "summary": "公式ドキュメント",
                "estimated_minutes": 30,
                "priority": "recommended",
            },
            {
                "kind": "book",
                "title": "no url",
                "url": None,
                "estimated_minutes": 60,
                "priority": "supplementary",
            },  # dropped (no url)
        ]

    monkeypatch.setattr(learning_plan_generation, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(learning_plan_generation, "GitHubGitClient", lambda access_token: _FakeClient())
    # 学習生成はエージェント経由（issue 263）。パイプラインテストでは orchestrator を直接差し替える。
    la = learning_plan_generation.learning_authoring
    monkeypatch.setattr(la, "generate_external_resources_agentic", _fake_external)
    monkeypatch.setattr(la, "generate_code_learning_steps_agentic", _fake_code_steps)


async def _seed_plan(session_maker: async_sessionmaker) -> uuid.UUID:
    async with session_maker() as session:
        plan = LearningPlan(project_id=uuid.uuid4(), gap_concepts=["cache"])
        session.add(plan)
        await session.commit()
        return plan.id


def _request(plan_id: uuid.UUID) -> LearningPlanGenerationRequest:
    return LearningPlanGenerationRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.LEARNING_PLAN_GENERATION,
        plan_id=str(plan_id),
        project_id=str(uuid.uuid4()),
        gap_concepts=["cache"],
        repo_full_name="acme/rosetta",
        branch="main",
        github=GitHubRef(installation_id=1),
        requested_by="u",
    )


async def test_generation_team_first_and_minutes(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    _patch(monkeypatch)
    plan_id = await _seed_plan(session_maker)
    async with session_maker() as session:
        result = await learning_plan_generation.process(_request(plan_id), PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    # Section A (code) = adr(0001-cache.md) + code(src/cache.py); Section B (stack) = 1 valid (no-url dropped)
    assert result.team_count == 2  # code section
    assert result.external_count == 1  # stack section
    assert result.step_count == 3

    async with session_maker() as session:
        steps = (
            (
                await session.execute(
                    select(LearningStep).where(LearningStep.plan_id == plan_id).order_by(LearningStep.order)
                )
            )
            .scalars()
            .all()
        )
        resources = {r.id: r for r in (await session.execute(select(LearningResource))).scalars().all()}
        sections = [resources[s.resource_id].section for s in steps]
        assert sections == ["code", "code", "stack"]  # A (code) then B (stack)
        # code ステップは Gemini の説明（summary）を持つ
        code_summaries = [resources[s.resource_id].summary for s in steps if resources[s.resource_id].section == "code"]
        assert "キャッシュ実装の要点" in code_summaries
        plan = (await session.execute(select(LearningPlan).where(LearningPlan.id == plan_id))).scalar_one()
        assert plan.estimated_total_minutes == 15 + 20 + 30


async def test_generation_idempotent(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch(monkeypatch)
    plan_id = await _seed_plan(session_maker)
    async with session_maker() as session:
        await learning_plan_generation.process(_request(plan_id), PipelineContext(session=session))
        await session.commit()
    async with session_maker() as session:
        await learning_plan_generation.process(_request(plan_id), PipelineContext(session=session))
        await session.commit()
    async with session_maker() as session:
        count = (
            await session.execute(select(func.count()).select_from(LearningStep).where(LearningStep.plan_id == plan_id))
        ).scalar_one()
        assert count == 3  # not duplicated
