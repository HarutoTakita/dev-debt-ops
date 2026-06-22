"""Knowledge-unit hub API (issue 063) — feature units (learning + confirmation quiz + KC)."""

from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import CurrentUser, OrgScope, SASessionDep
from app.schemas.knowledge_unit import KnowledgeUnitsOut
from app.services.knowledge_units import build_knowledge_units
from app.services.project import ProjectServiceDep

router = APIRouter(tags=["knowledge-units"])


@router.get(
    "/orgs/{slug}/projects/{project_slug}/knowledge-units",
    response_model=KnowledgeUnitsOut,
    summary="機能（feature）単位の学習×確認クイズ単元を返す",
)
async def get_knowledge_units(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> KnowledgeUnitsOut:
    """Return the caller's feature units (learn→confirm). Empty when feature clustering未実行."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    units = await build_knowledge_units(session, project, current_user.id)
    return KnowledgeUnitsOut(units=units)
