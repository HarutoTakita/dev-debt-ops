"""Server-side learning-plan + baseline-quiz generation for the agentic job (issue 069, Increment 2).

After the agentic job clusters features, generate — for the run's requester — one learning plan and
one baseline quiz per feature. This is the same per-feature fan-out the api ``baseline-plans`` /
``baseline-quizzes`` endpoints do, but performed inside the single analysis job so there is no
browser-driven orchestration (a closed tab / expired session no longer leaves learning & quizzes
ungenerated). Reuses ``learning_plan_generation.process`` / ``quiz_generation.process`` (which only
``flush``; ``run_task`` owns the terminal commit). Idempotent per ``(project, developer, feature)``.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service.pipelines import learning_plan_generation, quiz_generation
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, LearningPlan, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest
from shared.schemas.learning_plan import LearningPlanGenerationRequest
from shared.schemas.quiz import QuizGenerationRequest

logger = logging.getLogger(__name__)


async def _latest_feature_run(session: AsyncSession, project_id: uuid.UUID) -> AnalysisRun | None:
    """The latest COMPLETED feature_clustering run for the project (the one the backbone just made)."""
    return (
        await session.execute(
            select(AnalysisRun)
            .where(
                col(AnalysisRun.project_id) == project_id,
                col(AnalysisRun.kind) == JobType.FEATURE_CLUSTERING.value,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _generate_plan(
    session: AsyncSession,
    ctx: PipelineContext,
    request: AgenticAnalysisRequest,
    feature: Feature,
    developer_id: uuid.UUID,
) -> None:
    """Create + fill a learning plan for one feature (skip if the requester already has one)."""
    existing = (
        await session.execute(
            select(LearningPlan).where(
                col(LearningPlan.project_id) == feature.project_id,
                col(LearningPlan.developer_id) == developer_id,
                col(LearningPlan.feature_id) == feature.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    plan = LearningPlan(
        project_id=feature.project_id, developer_id=developer_id, feature_id=feature.id, gap_concepts=[]
    )
    session.add(plan)
    await session.flush()
    await learning_plan_generation.process(
        LearningPlanGenerationRequest(
            job_id=request.job_id,
            job_type=JobType.LEARNING_PLAN_GENERATION,
            plan_id=str(plan.id),
            project_id=request.project_id,
            gap_concepts=[],
            repo_full_name=f"{request.owner}/{request.repo}",
            branch=request.branch,
            github=request.github,
            requested_by=request.requested_by,
        ),
        ctx,
    )


async def _generate_quiz(
    session: AsyncSession,
    ctx: PipelineContext,
    request: AgenticAnalysisRequest,
    feature: Feature,
    developer_id: uuid.UUID,
) -> None:
    """Create + fill a baseline quiz for one feature (skip if the requester has an open one)."""
    existing = (
        await session.execute(
            select(QuizSession).where(
                col(QuizSession.project_id) == feature.project_id,
                col(QuizSession.developer_id) == developer_id,
                col(QuizSession.feature_id) == feature.id,
                col(QuizSession.is_baseline).is_(True),
                col(QuizSession.status) != "completed",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    rep = (
        await session.execute(
            select(FeatureFile)
            .where(col(FeatureFile.feature_id) == feature.id)
            .order_by(col(FeatureFile.confidence).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    repo_full = f"{request.owner}/{request.repo}"
    quiz = QuizSession(
        project_id=feature.project_id,
        developer_id=developer_id,
        file_path=rep.file_path if rep is not None else "",
        repo_full_name=repo_full,
        granularity="feature",
        feature_id=feature.id,
        is_baseline=True,
        status="not_started",
    )
    session.add(quiz)
    await session.flush()
    await quiz_generation.process(
        QuizGenerationRequest(
            job_id=request.job_id,
            job_type=JobType.QUIZ_GENERATION,
            session_id=str(quiz.id),
            project_id=request.project_id,
            file_path=quiz.file_path,
            repo_full_name=repo_full,
            branch=request.branch,
            github=request.github,
            requested_by=request.requested_by,
            granularity="feature",
            feature_id=str(feature.id),
        ),
        ctx,
    )


async def generate_learning_and_quizzes(request: AgenticAnalysisRequest, ctx: PipelineContext) -> list[str]:
    """Generate a learning plan + baseline quiz per clustered feature, for the run's requester."""
    session = ctx.session
    if session is None:
        return []
    try:
        developer_id = uuid.UUID(request.requested_by)
    except ValueError:
        return ["[generate] requested_by が不正のため学習/クイズ生成をスキップ"]

    project_id = uuid.UUID(request.project_id)
    run = await _latest_feature_run(session, project_id)
    if run is None:
        return ["[generate] 機能クラスタ未完了のため学習/クイズ生成をスキップ"]

    features = (await session.execute(select(Feature).where(col(Feature.run_id) == run.id))).scalars().all()
    steps: list[str] = []
    for feature in features:
        try:
            await _generate_plan(session, ctx, request, feature, developer_id)
            steps.append(f"[generate] learning plan: {feature.key}")
        except Exception as exc:  # one feature failing must not abort the rest
            logger.exception("learning plan generation failed for feature %s", feature.key)
            steps.append(f"[generate] learning plan {feature.key} failed: {exc}")
        try:
            await _generate_quiz(session, ctx, request, feature, developer_id)
            steps.append(f"[generate] quiz: {feature.key}")
        except Exception as exc:
            logger.exception("quiz generation failed for feature %s", feature.key)
            steps.append(f"[generate] quiz {feature.key} failed: {exc}")
    return steps
