"""issue 035: learning-plan generation — team-first ordering + idempotency (GitHub/Gemini mocked)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import learning_plan_generation
from service.services import gemini_stack_service
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

    async def _fake_external(gap_concepts: list[str]) -> list[dict]:
        return [
            {
                "kind": "docs",
                "title": "Caching docs",
                "url": "https://example.com/cache",
                "estimated_minutes": 30,
                "priority": "recommended",
            },
            {
                "kind": "book",
                "title": "no url",
                "url": None,
                "estimated_minutes": 60,
                "priority": "supplementary",
            },  # dropped
        ]

    monkeypatch.setattr(learning_plan_generation, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(learning_plan_generation, "GitHubGitClient", lambda access_token: _FakeClient())
    monkeypatch.setattr(gemini_stack_service, "generate_external_resources", _fake_external)


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

    # team = adr(0001-cache.md) + code(src/cache.py); external = 1 valid (no-url dropped)
    assert result.team_count == 2
    assert result.external_count == 1
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
        origins = [resources[s.resource_id].origin for s in steps]
        assert origins == ["team", "team", "external"]  # team first
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
