"""Server-side learning-plan + baseline-quiz generation for the agentic job (issue 069, Increment 2).

After the agentic job clusters features, generate — for the run's requester — one learning plan and
one baseline quiz per feature. This is the same per-feature fan-out the api ``baseline-plans`` /
``baseline-quizzes`` endpoints do, but performed inside the single analysis job so there is no
browser-driven orchestration (a closed tab / expired session no longer leaves learning & quizzes
ungenerated). Reuses the ``prepare_inputs`` / ``generate`` / ``persist`` stages of
``learning_plan_generation`` / ``quiz_generation``. Idempotent per ``(project, developer, feature)``.

Concurrency (issue: parallelise learning/quiz generation): the whole agentic job runs on one shared
session with a single terminal commit (issue-042), and the features it reads are only *flushed*, not
committed — so we cannot fan out onto independent sessions. Instead we split into three phases:

1. **prepare** (serial, on the session): dedup + read each feature's generation inputs. Read-only.
2. **generate** (concurrent, session-free): the slow Gemini authoring, capped by a semaphore
   (``config.baseline_fanout_concurrency()``). Each Gemini call already retries 429/5xx with jittered
   backoff, so a modest cap keeps quota pressure bounded and no feature fails the run.
3. **persist** (serial, per-feature SAVEPOINT): create the plan/quiz row + write its children. A
   feature (or one of its two kinds) failing is isolated to its savepoint and never aborts the rest.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.pipelines import learning_plan_generation, quiz_generation
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, LearningPlan, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest
from shared.schemas.learning_plan import LearningPlanGenerationRequest

logger = logging.getLogger(__name__)


@dataclass
class _FeatureWork:
    """Per-feature state threaded across the prepare → generate → persist phases.

    ``*_inputs is None`` means "skip this kind" (already exists, or prepare/generate failed) — so the
    persist phase never creates a row for it.
    """

    feature: Feature
    plan_inputs: learning_plan_generation.PlanInputs | None = None
    plan_generated: learning_plan_generation.PlanGenerated | None = None
    quiz_inputs: quiz_generation.QuizInputs | None = None
    quiz_generated: dict | None = None


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


async def _plan_exists(session: AsyncSession, feature: Feature, developer_id: uuid.UUID) -> bool:
    """The requester already has a learning plan for this feature (skip regeneration)."""
    existing = (
        await session.execute(
            select(LearningPlan).where(
                col(LearningPlan.project_id) == feature.project_id,
                col(LearningPlan.developer_id) == developer_id,
                col(LearningPlan.feature_id) == feature.id,
            )
        )
    ).scalar_one_or_none()
    return existing is not None


async def _quiz_exists(session: AsyncSession, feature: Feature, developer_id: uuid.UUID) -> bool:
    """The requester already has a baseline quiz for this feature (any status) — dedup (issue 075-B).

    ``limit(1).first()`` so a pre-existing duplicate (from an old bug) doesn't raise MultipleResultsFound.
    """
    existing = (
        (
            await session.execute(
                select(QuizSession)
                .where(
                    col(QuizSession.project_id) == feature.project_id,
                    col(QuizSession.developer_id) == developer_id,
                    col(QuizSession.feature_id) == feature.id,
                    col(QuizSession.is_baseline).is_(True),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return existing is not None


async def _persist_plan(
    session: AsyncSession,
    ctx: PipelineContext,
    request: AgenticAnalysisRequest,
    feature: Feature,
    developer_id: uuid.UUID,
    work: _FeatureWork,
) -> None:
    """Create the LearningPlan row + persist its resources/steps (run inside a per-feature savepoint)."""
    if work.plan_inputs is None or work.plan_generated is None:
        return
    plan = LearningPlan(
        project_id=feature.project_id, developer_id=developer_id, feature_id=feature.id, gap_concepts=[]
    )
    session.add(plan)
    await session.flush()
    plan_request = LearningPlanGenerationRequest(
        job_id=request.job_id,
        job_type=JobType.LEARNING_PLAN_GENERATION,
        plan_id=str(plan.id),
        project_id=request.project_id,
        gap_concepts=[],
        repo_full_name=f"{request.owner}/{request.repo}",
        branch=request.branch,
        github=request.github,
        requested_by=request.requested_by,
    )
    await learning_plan_generation.persist(session, plan_request, ctx, work.plan_inputs, work.plan_generated, plan=plan)


async def _persist_quiz(
    session: AsyncSession,
    request: AgenticAnalysisRequest,
    feature: Feature,
    developer_id: uuid.UUID,
    repo_full: str,
    work: _FeatureWork,
) -> None:
    """Create the baseline QuizSession row + persist its questions (run inside a per-feature savepoint).

    A skipped quiz (no code content → ``quiz_generated is None``) still creates the row so a re-run
    dedups it, matching the previous behaviour.
    """
    if work.quiz_inputs is None:
        return
    rep = (
        await session.execute(
            select(FeatureFile)
            .where(col(FeatureFile.feature_id) == feature.id)
            .order_by(col(FeatureFile.confidence).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
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
    await quiz_generation.persist(session, work.quiz_inputs, work.quiz_generated, quiz=quiz)


async def generate_learning_and_quizzes(
    request: AgenticAnalysisRequest,
    ctx: PipelineContext,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[str]:
    """Generate a learning plan + baseline quiz per clustered feature, for the run's requester.

    ``on_progress(done, total)`` (optional) is awaited after each feature is persisted so the caller
    can surface per-feature progress (e.g. "学習・クイズ生成 2/5") on the live cockpit.
    """
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
    total = len(features)
    if on_progress is not None:
        await on_progress(0, total)
    steps: list[str] = []
    repo_full = f"{request.owner}/{request.repo}"

    # Phase 1 — prepare (serial, read-only): dedup + gather generation inputs per feature.
    works: list[_FeatureWork] = []
    for feature in features:
        work = _FeatureWork(feature=feature)
        if not await _plan_exists(session, feature, developer_id):
            try:
                work.plan_inputs = await learning_plan_generation.prepare_inputs(
                    session,
                    ctx,
                    feature=feature,
                    repo_full_name=repo_full,
                    branch=request.branch,
                    github=request.github,
                    gap_concepts=[],
                )
            except Exception as exc:  # a prepare failure isolates to this feature's plan
                logger.exception("learning plan prepare failed for feature %s", feature.key)
                steps.append(f"[generate] learning plan {feature.key} failed: {exc}")
        if not await _quiz_exists(session, feature, developer_id):
            try:
                work.quiz_inputs = await quiz_generation.prepare_inputs(
                    session,
                    ctx,
                    granularity="feature",
                    feature_id=str(feature.id),
                    file_path="",
                    repo_full_name=repo_full,
                    branch=request.branch,
                    github=request.github,
                )
            except Exception as exc:
                logger.exception("quiz prepare failed for feature %s", feature.key)
                steps.append(f"[generate] quiz {feature.key} failed: {exc}")
        works.append(work)

    # Phase 2 — generate (concurrent, session-free): the slow Gemini authoring, capped by a semaphore.
    sem = asyncio.Semaphore(config.baseline_fanout_concurrency())

    async def _gen_plan(w: _FeatureWork, inputs: learning_plan_generation.PlanInputs) -> None:
        async with sem:
            w.plan_generated = await learning_plan_generation.generate(inputs)

    async def _gen_quiz(w: _FeatureWork, inputs: quiz_generation.QuizInputs) -> None:
        async with sem:
            w.quiz_generated = await quiz_generation.generate(inputs)

    gen_units: list[tuple[_FeatureWork, str]] = []
    coros = []
    for work in works:
        if work.plan_inputs is not None:
            gen_units.append((work, "plan"))
            coros.append(_gen_plan(work, work.plan_inputs))
        if work.quiz_inputs is not None:
            gen_units.append((work, "quiz"))
            coros.append(_gen_quiz(work, work.quiz_inputs))
    gen_results = await asyncio.gather(*coros, return_exceptions=True)
    for (work, kind), result in zip(gen_units, gen_results, strict=True):
        if isinstance(result, Exception):
            logger.error("%s generate failed for feature %s: %s", kind, work.feature.key, result)
            steps.append(f"[generate] {kind} {work.feature.key} failed: {result}")
            if kind == "plan":
                work.plan_inputs = None  # skip persist (no orphan row is created)
            else:
                work.quiz_inputs = None

    # Phase 3 — persist (serial, per-feature savepoint): create rows + write children; progress per feature.
    for index, work in enumerate(works):
        feature = work.feature
        if work.plan_inputs is not None:
            try:
                async with session.begin_nested():
                    await _persist_plan(session, ctx, request, feature, developer_id, work)
                steps.append(f"[generate] learning plan: {feature.key}")
            except Exception as exc:  # one feature failing must not abort the rest
                logger.exception("learning plan persist failed for feature %s", feature.key)
                steps.append(f"[generate] learning plan {feature.key} failed: {exc}")
        if work.quiz_inputs is not None:
            try:
                async with session.begin_nested():
                    await _persist_quiz(session, request, feature, developer_id, repo_full, work)
                steps.append(f"[generate] quiz: {feature.key}")
            except Exception as exc:
                logger.exception("quiz persist failed for feature %s", feature.key)
                steps.append(f"[generate] quiz {feature.key} failed: {exc}")
        if on_progress is not None:
            await on_progress(index + 1, total)
    return steps
