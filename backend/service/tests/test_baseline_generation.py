"""issue 069/075: server-side baseline fanout — per-feature savepoint isolation + baseline dedup.

The fanout (``generate_learning_and_quizzes``) runs learning-plan + baseline-quiz generation per
feature on one shared session, committed once by ``run_task``. These tests use fakes for the heavy
``learning_plan_generation.process`` / ``quiz_generation.process`` (GitHub + Gemini) and assert the
transaction-isolation (074-A savepoint) and idempotency (075-B) behaviour directly.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import baseline_generation
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, LearningPlan, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest
from shared.schemas.stack_analysis import GitHubRef


async def _seed_features(session_maker: async_sessionmaker, project_id: uuid.UUID, keys: list[str]) -> None:
    """Seed a COMPLETED feature_clustering run + one Feature (with a FeatureFile) per key."""
    async with session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.FEATURE_CLUSTERING.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        for k in keys:
            feat = Feature(project_id=project_id, run_id=run.id, key=k, name=k, description=f"{k} feature")
            session.add(feat)
            await session.flush()
            session.add(FeatureFile(run_id=run.id, feature_id=feat.id, file_path=f"src/{k}.py", confidence=0.9))
        await session.commit()


def _request(project_id: uuid.UUID, developer_id: uuid.UUID) -> AgenticAnalysisRequest:
    return AgenticAnalysisRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.AGENTIC_ANALYSIS,
        owner="acme",
        repo="rosetta",
        branch="main",
        project_id=str(project_id),
        github=GitHubRef(installation_id=1),
        requested_by=str(developer_id),
    )


async def test_fanout_creates_plan_and_quiz_per_feature(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """Happy path: each feature gets a LearningPlan + baseline QuizSession; on_progress ticks per feature."""
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    await _seed_features(session_maker, project_id, ["auth", "billing"])

    async def _ok(req: object, ctx: object) -> None:
        return None

    monkeypatch.setattr(baseline_generation.learning_plan_generation, "process", _ok)
    monkeypatch.setattr(baseline_generation.quiz_generation, "process", _ok)

    progress: list[tuple[int, int]] = []

    async def _on_progress(done: int, total: int) -> None:
        progress.append((done, total))

    async with session_maker() as session:
        await baseline_generation.generate_learning_and_quizzes(
            _request(project_id, developer_id), PipelineContext(session=session), on_progress=_on_progress
        )
        await session.commit()

    assert progress == [(0, 2), (1, 2), (2, 2)]
    async with session_maker() as session:
        plans = (await session.execute(select(func.count()).select_from(LearningPlan))).scalar_one()
        quizzes = (
            await session.execute(
                select(func.count()).select_from(QuizSession).where(QuizSession.is_baseline.is_(True))
            )
        ).scalar_one()
        assert plans == 2
        assert quizzes == 2


async def test_failed_feature_rolls_back_and_regenerates_on_rerun(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """075-A: a feature whose plan generation raises leaves NO partial LearningPlan (savepoint rollback),
    the other feature is unaffected, and a re-run regenerates the failed one (not locked to empty)."""
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    await _seed_features(session_maker, project_id, ["auth", "billing"])

    calls = {"plan": 0}

    async def _plan_process(req: object, ctx: object) -> None:
        calls["plan"] += 1
        if calls["plan"] == 1:  # 最初の 1 機能だけ失敗させる（LearningPlan は _generate_plan で flush 済み）
            raise RuntimeError("gemini boom")
        return None

    async def _quiz_ok(req: object, ctx: object) -> None:
        return None

    monkeypatch.setattr(baseline_generation.learning_plan_generation, "process", _plan_process)
    monkeypatch.setattr(baseline_generation.quiz_generation, "process", _quiz_ok)

    # 1st run: one feature's plan fails → its empty LearningPlan must be rolled back to the savepoint.
    async with session_maker() as session:
        await baseline_generation.generate_learning_and_quizzes(
            _request(project_id, developer_id), PipelineContext(session=session)
        )
        await session.commit()
    async with session_maker() as session:
        assert (await session.execute(select(func.count()).select_from(LearningPlan))).scalar_one() == 1

    # 2nd run: the failed feature is regenerated (existence guard didn't lock it to an empty plan).
    async with session_maker() as session:
        await baseline_generation.generate_learning_and_quizzes(
            _request(project_id, developer_id), PipelineContext(session=session)
        )
        await session.commit()
    async with session_maker() as session:
        assert (await session.execute(select(func.count()).select_from(LearningPlan))).scalar_one() == 2


async def test_completed_baseline_quiz_is_not_regenerated(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """075-B: a COMPLETED baseline quiz dedups too — a re-run does not create a duplicate is_baseline session."""
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    await _seed_features(session_maker, project_id, ["auth"])

    async with session_maker() as session:
        feat = (await session.execute(select(Feature).where(Feature.project_id == project_id))).scalar_one()
        session.add(
            QuizSession(
                project_id=project_id,
                developer_id=developer_id,
                file_path="src/auth.py",
                repo_full_name="acme/rosetta",
                granularity="feature",
                feature_id=feat.id,
                is_baseline=True,
                status="completed",  # 完了済み baseline が既に存在
            )
        )
        await session.commit()

    async def _ok(req: object, ctx: object) -> None:
        return None

    monkeypatch.setattr(baseline_generation.learning_plan_generation, "process", _ok)
    monkeypatch.setattr(baseline_generation.quiz_generation, "process", _ok)

    async with session_maker() as session:
        await baseline_generation.generate_learning_and_quizzes(
            _request(project_id, developer_id), PipelineContext(session=session)
        )
        await session.commit()

    async with session_maker() as session:
        n = (
            await session.execute(
                select(func.count()).select_from(QuizSession).where(QuizSession.is_baseline.is_(True))
            )
        ).scalar_one()
        assert n == 1  # 重複生成されない（修正前は 2）
