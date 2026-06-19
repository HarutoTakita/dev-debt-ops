"""Overview aggregation API (issue 031).

``GET .../overview`` aggregates the latest code-debt + KC runs (issues 028/029) and the
``debt_trend_points`` snapshots into the ``overviewSchema`` payload. Read-only; returns an empty
(200) payload when nothing has been analysed yet. Project-scoped under ``OrgScope``.
"""

from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import OrgScope, SASessionDep
from app.schemas.overview import OverviewOut
from app.services.debt_query import build_overview
from app.services.project import ProjectServiceDep

router = APIRouter(tags=["overview"])


@router.get(
    "/orgs/{slug}/projects/{project_slug}/overview",
    response_model=OverviewOut,
    summary="Overview 二軸ダッシュボードの集計を返す",
)
async def get_overview(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> OverviewOut:
    """Return the project's two-axis overview (files / trend / activity). 200 even when empty."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    return await build_overview(session, project, org.slug)
