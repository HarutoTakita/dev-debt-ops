"""Twin-Agent API (issue 036) — loop run (202) + activity/pipeline delivery + node retry.

Project-scoped under ``OrgScope`` (profiles are static + org-independent). The loop runs as a service
pipeline; activities/pipelines are read from the loop tables for polling. snake_case ``BaseModel``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import CurrentUser, OrgScope, SASessionDep, SessionDep
from app.api.v1.github import InstallationIdDep
from app.schemas.agent import (
    AgentActivityOut,
    AgentPipelineOut,
    AgentProfileOut,
    NarrativeEvidenceOut,
    NarrativeStepOut,
)
from app.schemas.job import JobEnqueuedOut
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.job_orchestrator import enqueue_job
from app.services.project import ProjectServiceDep
from shared.enums import JobType
from shared.models import AgentActivity, AgentPipeline, NarrativeEvidence, NarrativeStep
from shared.queue import BlobClient, TaskDispatcher

router = APIRouter(tags=["agents"])

_KIND_TO_JOB = {"code_debt": JobType.CODE_DEBT_LOOP, "knowledge_debt": JobType.KNOWLEDGE_DEBT_LOOP}

# Static agent personas (no table; org-independent — issue 036 design).
_PROFILES = [
    AgentProfileOut(
        kind="code_debt",
        name="アーキ考古学者",
        role="Code Debt Agent",
        accent="debt-code",
        tagline="私はコードの地層を掘り、負債の初出コミットまで遡る。",
    ),
    AgentProfileOut(
        kind="knowledge_debt",
        name="知識の司書",
        role="Knowledge Debt Agent",
        accent="debt-knowledge",
        tagline="私はチームの理解の空白を見つけ、学びへ橋渡しする。",
    ),
]


def _as_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="見つかりません") from e


async def _activity_out(db: AsyncSession, activity: AgentActivity) -> AgentActivityOut:
    steps = (
        (
            await db.execute(
                select(NarrativeStep)
                .where(col(NarrativeStep.activity_id) == activity.id)
                .order_by(col(NarrativeStep.order))
            )
        )
        .scalars()
        .all()
    )
    step_out = []
    for s in steps:
        evidence = (
            (await db.execute(select(NarrativeEvidence).where(col(NarrativeEvidence.step_id) == s.id))).scalars().all()
        )
        step_out.append(
            NarrativeStepOut(
                id=str(s.id),
                status=s.status,
                message=s.message,
                created_at=s.created_at,
                evidence=[
                    NarrativeEvidenceOut(type=e.type, label=e.label, detail=e.detail, href=e.href) for e in evidence
                ],
            )
        )
    return AgentActivityOut(
        id=str(activity.id),
        kind=activity.kind,
        headline=activity.headline,
        steps=step_out,
        pipeline_id=str(activity.pipeline_id),
        created_at=activity.created_at,
    )


@router.get("/agents/profiles", response_model=list[AgentProfileOut], summary="エージェント人格（静的）")
async def list_profiles(current_user: CurrentUser) -> list[AgentProfileOut]:
    """Return the static agent personas (org-independent)."""
    return _PROFILES


@router.post(
    "/orgs/{slug}/projects/{project_slug}/agents/{kind}/run",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Twin Agent 自律ループを enqueue する",
)
async def run_agent_loop(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    kind: str,
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Enqueue the code/knowledge debt loop for the project."""
    if kind not in _KIND_TO_JOB:
        raise HTTPException(status_code=422, detail="kind は code_debt / knowledge_debt のいずれか")
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    payload = {
        "project_id": str(project.id),
        "owner": project.repo_owner,
        "repo": project.repo_name,
        "branch": project.default_branch or "main",
        "kind": kind,
        "requested_by": str(current_user.id),
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=_KIND_TO_JOB[kind],
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/agents/activities",
    response_model=list[AgentActivityOut],
    summary="エージェント活動一覧",
)
async def list_activities(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
    kind: Annotated[str | None, Query()] = None,
) -> list[AgentActivityOut]:
    """Return the project's agent activities (optionally filtered by kind), newest first."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    stmt = select(AgentActivity).where(col(AgentActivity.project_id) == project.id)
    if kind:
        stmt = stmt.where(col(AgentActivity.kind) == kind)
    stmt = stmt.order_by(col(AgentActivity.created_at).desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [await _activity_out(session, a) for a in rows]


@router.get(
    "/orgs/{slug}/projects/{project_slug}/agents/activities/{activity_id}",
    response_model=AgentActivityOut,
    summary="エージェント活動詳細",
)
async def get_activity(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    activity_id: str,
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> AgentActivityOut:
    """Return one activity with its steps + evidence."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    activity = (
        await session.execute(select(AgentActivity).where(col(AgentActivity.id) == activity_id))
    ).scalar_one_or_none()
    if activity is None or activity.project_id != project.id:
        raise HTTPException(status_code=404, detail="活動が見つかりません")
    return await _activity_out(session, activity)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/agents/pipelines/{pipeline_id}",
    response_model=AgentPipelineOut,
    summary="エージェントパイプライン（ライブ状態）",
)
async def get_pipeline(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    pipeline_id: str,
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> AgentPipelineOut:
    """Return one pipeline's 5-stage state (poll alongside GET /jobs/{id})."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    pipeline = (
        await session.execute(select(AgentPipeline).where(col(AgentPipeline.id) == pipeline_id))
    ).scalar_one_or_none()
    if pipeline is None or pipeline.project_id != project.id:
        raise HTTPException(status_code=404, detail="パイプラインが見つかりません")
    return AgentPipelineOut(id=str(pipeline.id), kind=pipeline.kind, stages=list(pipeline.stages))


@router.post(
    "/orgs/{slug}/projects/{project_slug}/agents/pipelines/{pipeline_id}/nodes/{node_id}/retry",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="失敗ノードを再実行する",
)
async def retry_node(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    pipeline_id: str,
    node_id: str,
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Re-run a failed (retryable) node by re-enqueuing the loop and marking the node ``analyzing``."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    pipeline = await session.get(AgentPipeline, _as_uuid(pipeline_id))
    if pipeline is None or pipeline.project_id != project.id:
        raise HTTPException(status_code=404, detail="パイプラインが見つかりません")

    node = None
    for stage in pipeline.stages:
        for n in stage.get("nodes", []):
            if n.get("id") == node_id:
                node = n
                break
    if node is None:
        raise HTTPException(status_code=404, detail="ノードが見つかりません")
    if not node.get("retryable"):
        raise HTTPException(status_code=409, detail="このノードは再実行できません")

    node["status"] = "analyzing"
    node["retryable"] = False
    pipeline.stages = list(pipeline.stages)  # reassign so the JSON column is marked dirty
    session.add(pipeline)
    payload = {
        "project_id": str(project.id),
        "owner": project.repo_owner,
        "repo": project.repo_name,
        "branch": project.default_branch or "main",
        "kind": pipeline.kind,
        "requested_by": str(current_user.id),
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=_KIND_TO_JOB[pipeline.kind],
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)
