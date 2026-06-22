"""Overview aggregation API (issue 031).

``GET .../overview`` aggregates the latest code-debt + KC runs (issues 028/029) and the
``debt_trend_points`` snapshots into the ``overviewSchema`` payload. Read-only; returns an empty
(200) payload when nothing has been analysed yet. Project-scoped under ``OrgScope``.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import OrgScope, SASessionDep
from app.schemas.overview import AnalysisJobStatusOut, AnalysisStatusOut, FileDebtOut, OverviewOut
from app.services.debt_query import build_feature_drilldown, build_overview
from app.services.project import ProjectServiceDep
from shared.enums import JobType
from shared.models import Job

router = APIRouter(tags=["overview"])

_GRANULARITIES = {"feature", "folder", "file"}

# Analysis stages whose latest Job status we surface so the frontend cockpit can rehydrate after a
# reload (the run store is in-memory). One JobType per cockpit stage (issue 037 stages).
_ANALYSIS_JOB_TYPES = [
    JobType.CODE_DEBT_DETECTION,
    JobType.KNOWLEDGE_DEBT_DETECTION,
    JobType.KC_ANALYSIS,
    JobType.LEARNING_PLAN_GENERATION,
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
