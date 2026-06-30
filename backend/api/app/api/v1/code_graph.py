"""Code-graph API (issue 235).

``GET .../code-graph`` returns the project's latest CodeGraphContext snapshot (node-link function
call graph), persisted by the ``agentic_analysis`` pipeline. Read-only; ``observed=false`` (empty)
when no analysis has built a graph yet. The graph is built/persisted by the agentic analysis run —
there is no separate trigger endpoint here.
"""

from typing import Annotated

from fastapi import APIRouter, Path
from sqlalchemy import select

from app.api.deps import CurrentUser, OrgScope, SASessionDep
from app.schemas.code_graph import CodeGraphOut
from app.services.project import ProjectServiceDep
from shared.models import CodeGraph

router = APIRouter(tags=["code-graph"])


@router.get(
    "/orgs/{slug}/projects/{project_slug}/code-graph",
    response_model=CodeGraphOut,
    summary="コードグラフ（CodeGraphContext スナップショット）を返す",
)
async def get_code_graph(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> CodeGraphOut:
    """Return the project's latest code-graph snapshot. 200 with ``observed=false`` when not yet built."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    row = (
        await session.execute(select(CodeGraph).where(CodeGraph.project_id == project.id))  # ty: ignore[invalid-argument-type]
    ).scalar_one_or_none()
    if row is None:
        return CodeGraphOut(observed=False)
    graph = row.graph or {}
    return CodeGraphOut(observed=True, computed_at=row.computed_at, file_edges=graph.get("file_edges", []))
