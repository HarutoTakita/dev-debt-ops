"""Overview aggregation API (issue 031).

``GET .../overview`` aggregates the latest code-debt + KC runs (issues 028/029) and the
``debt_trend_points`` snapshots into the ``overviewSchema`` payload. Read-only; returns an empty
(200) payload when nothing has been analysed yet. Project-scoped under ``OrgScope``.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from app.api.deps import OrgScope, SASessionDep
from app.schemas.overview import FileDebtOut, OverviewOut
from app.services.debt_query import build_feature_drilldown, build_overview
from app.services.project import ProjectServiceDep

router = APIRouter(tags=["overview"])

_GRANULARITIES = {"feature", "folder", "file"}


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
