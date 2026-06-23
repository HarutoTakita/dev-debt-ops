"""Learning-plan API (issue 035) — generate (202) + get + step progress PATCH.

Project-scoped under ``OrgScope``. Generation runs as a service pipeline; the plan row is created up
front so its ``plan_id`` is returned immediately (the frontend polls ``GET /jobs/{id}`` then reads the
plan). ``gap_concepts`` come from issue 034's ``quiz_results`` (via ``attempt_id``) or the request body.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlmodel import col
from sqlmodel import select as sm_select

from app.api.deps import CurrentUser, OrgScope, SASessionDep, SessionDep
from app.api.v1.github import InstallationIdDep
from app.schemas.learning import (
    BaselinePlansOut,
    GeneratePlanIn,
    LearningPlanJobOut,
    LearningPlanOut,
    LearningResourceOut,
    LearningStepOut,
    StepPatchIn,
)
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.job_orchestrator import enqueue_job
from app.services.project import ProjectServiceDep
from shared.enums import JobStatus, JobType
from shared.models import (
    AnalysisRun,
    Feature,
    LearningPlan,
    LearningResource,
    LearningStep,
    QuizResult,
    QuizSession,
)
from shared.queue import BlobClient, TaskDispatcher

router = APIRouter(tags=["learning"])


async def _plan_out(db, plan: LearningPlan) -> LearningPlanOut:
    steps = (
        (
            await db.execute(
                select(LearningStep).where(col(LearningStep.plan_id) == plan.id).order_by(col(LearningStep.order))
            )
        )
        .scalars()
        .all()
    )
    resource_ids = [s.resource_id for s in steps]
    resources = {}
    if resource_ids:
        rows = (
            (await db.execute(select(LearningResource).where(col(LearningResource.id).in_(resource_ids))))
            .scalars()
            .all()
        )
        resources = {r.id: r for r in rows}
    step_out = []
    for s in steps:
        r = resources.get(s.resource_id)
        if r is None:
            continue
        step_out.append(
            LearningStepOut(
                order=s.order,
                completed=s.completed,
                resource=LearningResourceOut(
                    id=str(r.id),
                    origin=r.origin,
                    kind=r.kind,
                    title=r.title,
                    source_ref=r.source_ref,
                    url=r.url,
                    estimated_minutes=r.estimated_minutes,
                    priority=r.priority,
                    dormant_days=r.dormant_days,
                ),
            )
        )
    return LearningPlanOut(
        id=str(plan.id),
        gap_concepts=list(plan.gap_concepts),
        steps=step_out,
        estimated_total_minutes=plan.estimated_total_minutes,
    )


@router.post(
    "/orgs/{slug}/projects/{project_slug}/learning/plans",
    response_model=LearningPlanJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="学習プラン生成を enqueue する（plan_id を即時発番）",
)
async def create_learning_plan(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
    body: GeneratePlanIn | None = None,
    attempt_id: Annotated[uuid.UUID | None, Query()] = None,
) -> LearningPlanJobOut:
    """Create the plan row, enqueue generation, and return job + plan_id.

    ``gap_concepts`` resolve from the quiz attempt's ``quiz_results`` (``attempt_id``) when present,
    else from the request body (interim path until grading is always available).
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)

    gap_concepts: list[str] = list(body.gap_concepts) if body else []
    if attempt_id is not None:
        # Verify the quiz attempt belongs to this project AND this caller before reading its
        # gap_concepts (issue-040: previously any attempt_id was accepted → cross-user/tenant leak).
        qs = (await session.exec(sm_select(QuizSession).where(col(QuizSession.id) == attempt_id))).one_or_none()
        if qs is None or qs.project_id != project.id:
            raise HTTPException(status_code=404, detail="クイズが見つかりません")
        if qs.developer_id != current_user.id:
            raise HTTPException(status_code=403, detail="このクイズにアクセスする権限がありません")
        qr = (await session.exec(sm_select(QuizResult).where(col(QuizResult.session_id) == attempt_id))).one_or_none()
        if qr is not None:
            gap_concepts = [c["id"] for c in qr.gap_concepts if isinstance(c, dict) and "id" in c]

    plan = LearningPlan(
        project_id=project.id,
        developer_id=current_user.id,
        feature_id=uuid.UUID(body.feature_id) if body and body.feature_id else None,
        gap_concepts=gap_concepts,
        quiz_session_id=attempt_id,
    )
    session.add(plan)
    await session.flush()
    payload = {
        "plan_id": str(plan.id),
        "project_id": str(project.id),
        "gap_concepts": gap_concepts,
        "quiz_session_id": str(attempt_id) if attempt_id else None,
        "repo_full_name": project.repo_full_name,
        "branch": project.default_branch or "main",
        "requested_by": str(current_user.id),
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=JobType.LEARNING_PLAN_GENERATION,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return LearningPlanJobOut(job_id=job.id, status=job.status, plan_id=plan.id)


@router.post(
    "/orgs/{slug}/projects/{project_slug}/baseline-plans",
    response_model=BaselinePlansOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="機能ごとの学習プランを一括生成する（自分の分）",
)
async def generate_baseline_plans(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> BaselinePlansOut:
    """Create one learning plan per clustered feature for the caller and enqueue generation (issue 064).

    Consolidates generation under the single "解析" trigger: ``runAll`` calls this so every feature gets a
    plan. Self-scoped + idempotent (a feature that already has a plan for the caller is skipped) so re-runs
    don't fan out duplicates. 409 if feature clustering (issue 052) has not run yet. Mirrors
    ``baseline-quizzes``.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    run = (
        await session.exec(
            sm_select(AnalysisRun)
            .where(
                col(AnalysisRun.project_id) == project.id,
                col(AnalysisRun.kind) == JobType.FEATURE_CLUSTERING.value,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).first()
    if run is None:
        raise HTTPException(status_code=409, detail="機能クラスタリングが未実行です")

    features = (await session.exec(sm_select(Feature).where(col(Feature.run_id) == run.id))).all()
    job_ids: list[str] = []
    for feat in features:
        existing = (
            await session.exec(
                sm_select(LearningPlan).where(
                    col(LearningPlan.project_id) == project.id,
                    col(LearningPlan.developer_id) == current_user.id,
                    col(LearningPlan.feature_id) == feat.id,
                )
            )
        ).first()
        if existing is not None:
            continue  # already has a plan for this feature
        plan = LearningPlan(
            project_id=project.id,
            developer_id=current_user.id,
            feature_id=feat.id,
            gap_concepts=[],
        )
        session.add(plan)
        await session.flush()
        payload = {
            "plan_id": str(plan.id),
            "project_id": str(project.id),
            "gap_concepts": [],
            "quiz_session_id": None,
            "repo_full_name": project.repo_full_name,
            "branch": project.default_branch or "main",
            "requested_by": str(current_user.id),
            "github": {"installation_id": installation_id},
        }
        job = await enqueue_job(
            session=session,
            dispatcher=dispatcher,
            blob_client=blob,
            job_type=JobType.LEARNING_PLAN_GENERATION,
            payload=payload,
            created_by=current_user.id,
            project_id=project.id,
        )
        job_ids.append(str(job.id))
    return BaselinePlansOut(created=len(job_ids), job_ids=job_ids)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/learning/plans/{plan_id}",
    response_model=LearningPlanOut,
    summary="学習プランを返す（未生成は 404）",
)
async def get_learning_plan(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    plan_id: uuid.UUID,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> LearningPlanOut:
    """Return one learning plan with its ordered steps (team assets first). Owner-scoped."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    plan = (await session.execute(select(LearningPlan).where(col(LearningPlan.id) == plan_id))).scalar_one_or_none()
    if plan is None or plan.project_id != project.id:
        raise HTTPException(status_code=404, detail="学習プランが見つかりません")
    if plan.developer_id is not None and plan.developer_id != current_user.id:
        raise HTTPException(status_code=403, detail="この学習プランにアクセスする権限がありません")
    return await _plan_out(session, plan)


@router.patch(
    "/orgs/{slug}/projects/{project_slug}/learning/plans/{plan_id}/steps/{order}",
    response_model=LearningStepOut,
    summary="ステップの完了状態を部分更新する",
)
async def patch_learning_step(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    plan_id: uuid.UUID,
    order: int,
    body: StepPatchIn,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> LearningStepOut:
    """Patch a step's ``completed`` flag (and ``completed_at``). Owner-scoped."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    plan = (await session.execute(select(LearningPlan).where(col(LearningPlan.id) == plan_id))).scalar_one_or_none()
    if plan is None or plan.project_id != project.id:
        raise HTTPException(status_code=404, detail="学習プランが見つかりません")
    if plan.developer_id is not None and plan.developer_id != current_user.id:
        raise HTTPException(status_code=403, detail="この学習プランにアクセスする権限がありません")
    step = (
        await session.execute(
            select(LearningStep).where(col(LearningStep.plan_id) == plan_id, col(LearningStep.order) == order)
        )
    ).scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="ステップが見つかりません")

    step.completed = body.completed
    step.completed_at = datetime.now(UTC) if body.completed else None
    session.add(step)
    await session.commit()

    resource = (
        await session.execute(select(LearningResource).where(col(LearningResource.id) == step.resource_id))
    ).scalar_one()
    return LearningStepOut(
        order=step.order,
        completed=step.completed,
        resource=LearningResourceOut(
            id=str(resource.id),
            origin=resource.origin,
            kind=resource.kind,
            title=resource.title,
            source_ref=resource.source_ref,
            url=resource.url,
            estimated_minutes=resource.estimated_minutes,
            priority=resource.priority,
            dormant_days=resource.dormant_days,
        ),
    )
