"""Overview aggregation API (issue 031).

``GET .../overview`` aggregates the latest code-debt + KC runs (issues 028/029) and the
``debt_trend_points`` snapshots into the ``overviewSchema`` payload; returns an empty
(200) payload when nothing has been analysed yet. ``POST .../trend-snapshot`` records this week's
trend point after an analysis run (issue 067). Project-scoped under ``OrgScope``.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select, update
from sqlmodel import col

from app.api.deps import OrgScope, SASessionDep
from app.schemas.overview import AnalysisJobStatusOut, AnalysisStatusOut, DebtTrendPointOut, FileDebtOut, OverviewOut
from app.services.debt_query import build_feature_drilldown, build_overview, record_trend_snapshot
from app.services.project import ProjectServiceDep
from shared.enums import JobStatus, JobType
from shared.models import Job

router = APIRouter(tags=["overview"])

_GRANULARITIES = {"feature", "folder", "file"}

# Analysis stages whose latest Job status we surface so the frontend cockpit can rehydrate after a
# reload / re-login (the run store is in-memory). AGENTIC_ANALYSIS is the single cockpit stage in the
# issue-069 redesign — without it the cockpit reset to the "analyze" button on every reload. The
# legacy per-stage types stay so older runs / sub-pipeline jobs still rehydrate.
_ANALYSIS_JOB_TYPES = [
    JobType.AGENTIC_ANALYSIS,
    JobType.CODE_DEBT_DETECTION,
    JobType.KNOWLEDGE_DEBT_DETECTION,
    JobType.KC_ANALYSIS,
    JobType.FEATURE_CLUSTERING,
    JobType.LEARNING_PLAN_GENERATION,
    JobType.QUIZ_GENERATION,
]


@router.get(
    "/orgs/{slug}/projects/{project_slug}/overview",
    response_model=OverviewOut,
    summary="Overview 二軸ダッシュボードの集計を返す（粒度切替対応）",
)
async def get_overview(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
    granularity: Annotated[str, Query()] = "file",
) -> OverviewOut:
    """Return the two-axis overview. ``granularity=feature|folder|file`` (default ``file``, issue 055).

    ``feature``/``folder`` populate ``features`` (rolled-up nodes); ``files`` (file-level points)
    is always returned for backward compatibility.
    """
    if granularity not in _GRANULARITIES:
        raise HTTPException(status_code=422, detail="granularity は feature / folder / file のいずれか")
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    return await build_overview(session, project, org.slug, granularity=granularity)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/features/{feature_key}",
    response_model=list[FileDebtOut],
    summary="機能配下のファイル単位の理解負債を返す（ドリルダウン）",
)
async def get_feature_drilldown(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    feature_key: Annotated[str, Path(description="Feature key (slug).")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> list[FileDebtOut]:
    """Return the file-level points for one feature (issue 055). Empty list if the feature is unknown."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    return await build_feature_drilldown(session, project, feature_key)


@router.post(
    "/orgs/{slug}/projects/{project_slug}/trend-snapshot",
    response_model=DebtTrendPointOut | None,
    summary="解析時点のコード品質・理解度を週次推移点として記録する（upsert・issue 067）",
)
async def record_trend_snapshot_route(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> DebtTrendPointOut | None:
    """Record/upsert this week's trend point from current aggregates (issue 067).

    Called after the "Analyze" run completes so history accumulates over weeks. Returns the recorded
    point, or ``null`` when nothing has been analysed yet (no files → no snapshot).
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    return await record_trend_snapshot(session, project, org.slug)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/analysis-status",
    response_model=AnalysisStatusOut,
    summary="解析ステージごとの最新ジョブ状態を返す（リロード後の状態復元用）",
)
async def get_analysis_status(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> AnalysisStatusOut:
    """Return the latest Job status per analysis JobType for the project (keyed by JobType value).

    Lets the in-memory cockpit run store rehydrate stage status on page load: a project that has
    ever run a stage shows that stage's COMPLETED/FAILED/PROCESSING state instead of resetting.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    rows = (
        (
            await session.execute(
                select(Job)
                .where(col(Job.project_id) == project.id, col(Job.job_type).in_(_ANALYSIS_JOB_TYPES))
                .order_by(col(Job.created_at).desc())
            )
        )
        .scalars()
        .all()
    )
    jobs: dict[str, AnalysisJobStatusOut] = {}
    for j in rows:
        key = str(j.job_type)  # JobType is a StrEnum → value string
        if key not in jobs:  # rows are newest-first → first seen is the latest per type
            jobs[key] = AnalysisJobStatusOut(status=str(j.status), job_id=str(j.id))
    return AnalysisStatusOut(jobs=jobs)


@router.post(
    "/orgs/{slug}/projects/{project_slug}/cancel-analysis",
    response_model=AnalysisStatusOut,
    summary="進行中（QUEUED/PROCESSING）の解析ジョブをキャンセルし、最新状態を返す",
)
async def cancel_analysis(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> AnalysisStatusOut:
    """Cancel the project's in-progress analysis jobs so the cockpit can be unblocked.

    A QUEUED job that never dispatched (e.g. a stuck run) otherwise keeps the run store in a
    permanent "running" state, disabling the Analyze button with no way out from the UI. Marks
    QUEUED / PROCESSING analysis jobs CANCELLED; an already in-flight worker may still write its
    own terminal status afterward (best effort — we don't hard-kill a running pipeline).
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    await session.execute(
        update(Job)
        .where(
            col(Job.project_id) == project.id,
            col(Job.job_type).in_(_ANALYSIS_JOB_TYPES),
            col(Job.status).in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
        )
        .values(status=JobStatus.CANCELLED, completed_at=datetime.now(UTC))
    )
    await session.commit()
    rows = (
        (
            await session.execute(
                select(Job)
                .where(col(Job.project_id) == project.id, col(Job.job_type).in_(_ANALYSIS_JOB_TYPES))
                .order_by(col(Job.created_at).desc())
            )
        )
        .scalars()
        .all()
    )
    jobs: dict[str, AnalysisJobStatusOut] = {}
    for j in rows:
        key = str(j.job_type)
        if key not in jobs:
            jobs[key] = AnalysisJobStatusOut(status=str(j.status), job_id=str(j.id))
    return AnalysisStatusOut(jobs=jobs)
