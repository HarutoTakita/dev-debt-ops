"""Code-graph API (issue 235).

``GET .../code-graph`` returns the project's latest CodeGraphContext snapshot (node-link function
call graph), persisted by the ``agentic_analysis`` pipeline. Read-only; ``observed=false`` (empty)
when no analysis has built a graph yet. The graph is built/persisted by the agentic analysis run —
there is no separate trigger endpoint here.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, OrgScope, SASessionDep
from app.schemas.code_graph import CodeGraphOut, FileFunctionGraphOut
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


@router.get(
    "/orgs/{slug}/projects/{project_slug}/code-graph/file",
    response_model=FileFunctionGraphOut,
    summary="指定ファイル内の関数コールグラフ（Level-3）を返す",
)
async def get_file_function_graph(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
    path: Annotated[str, Query(description="Repo-relative file path to scope the function graph to.")],
) -> FileFunctionGraphOut:
    """Return one file's internal function call graph (lazily, on file click). Empty when unobserved."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    row = (
        await session.execute(select(CodeGraph).where(CodeGraph.project_id == project.id))  # ty: ignore[invalid-argument-type]
    ).scalar_one_or_none()
    if row is None:
        return FileFunctionGraphOut(observed=False)
    graph = row.graph or {}
    nodes = [{"id": fn["name"]} for fn in graph.get("functions", []) if fn.get("file") == path]
    edges = [
        {"source": c["source"], "target": c["target"]} for c in graph.get("function_calls", []) if c.get("file") == path
    ]
    return FileFunctionGraphOut(observed=True, nodes=nodes, edges=edges)
