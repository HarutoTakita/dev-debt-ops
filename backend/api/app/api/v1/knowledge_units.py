"""Knowledge-unit hub API (issue 063) — feature units (learning + confirmation quiz + KC)."""

from typing import Annotated

from fastapi import APIRouter, Path, Response, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col

from app.api.deps import CurrentUser, OrgScope, SASessionDep
from app.schemas.knowledge_unit import FeatureFlagIn, KnowledgeUnitsOut
from app.services.knowledge_units import build_knowledge_units
from app.services.project import ProjectServiceDep
from shared.models import FeatureFlag

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


@router.put(
    "/orgs/{slug}/projects/{project_slug}/knowledge-units/{feature_key}/flag",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="機能単元のフラグを設定/解除する（フラグ付きは一覧上部へ）",
)
async def set_feature_flag(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    feature_key: Annotated[str, Path(description="Stable feature key to flag.")],
    body: FeatureFlagIn,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> Response:
    """Set (upsert) or clear the caller's flag on a feature unit; persisted by feature_key."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    if body.flagged:
        stmt = pg_insert(FeatureFlag).values(
            developer_id=current_user.id, project_id=project.id, feature_key=feature_key
        )
        await session.execute(stmt.on_conflict_do_nothing(constraint="uq_feature_flags_dev_project_key"))
    else:
        await session.execute(
            delete(FeatureFlag).where(
                col(FeatureFlag.developer_id) == current_user.id,
                col(FeatureFlag.project_id) == project.id,
                col(FeatureFlag.feature_key) == feature_key,
            )
        )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
