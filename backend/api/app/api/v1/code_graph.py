"""Code-graph API (issue 235).

``GET .../code-graph`` returns the project's latest CodeGraphContext snapshot (node-link function
call graph), persisted by the ``agentic_analysis`` pipeline. Read-only; ``observed=false`` (empty)
when no analysis has built a graph yet. The graph is built/persisted by the agentic analysis run —
there is no separate trigger endpoint here.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentUser, OrgScope, SASessionDep
from app.schemas.code_graph import CodeGraphOut, FeatureFunctionGraphOut, FileFunctionGraphOut
from app.services.project import ProjectServiceDep
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, CodeGraph, Feature, FeatureFile

router = APIRouter(tags=["code-graph"])

# Bound the feature function-graph so the frontend's O(n²) force layout stays responsive (issue 282).
_MAX_FEATURE_NODES = 400


def _call_files(call: dict) -> tuple[str, str]:
    """Source/target file of a function-call edge, tolerating the pre-issue-282 ``{file,...}`` shape."""
    return call.get("source_file", call.get("file", "")), call.get("target_file", call.get("file", ""))


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
    edges = []
    for c in graph.get("function_calls", []):
        sf, tf = _call_files(c)
        if sf == path and tf == path and c.get("source") and c.get("target"):  # intra-file only for L3
            edges.append({"source": c["source"], "target": c["target"]})
    return FileFunctionGraphOut(observed=True, nodes=nodes, edges=edges)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/code-graph/feature",
    response_model=FeatureFunctionGraphOut,
    summary="機能の関数レベルグラフ（Level-2: ファイル=クラスタ, 関数=ノード）を返す",
)
async def get_feature_function_graph(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
    key: Annotated[str, Query(description="Feature key to scope the function graph to.")],
) -> FeatureFunctionGraphOut:
    """Return one feature's function-level graph (issue 282): file hubs + functions, CONTAINS + CALLS.

    Scoped to the feature's files (latest ``feature_clustering`` run). Every function attaches to its
    file hub via CONTAINS, so nothing floats disconnected; cross-file CALLS connect the clusters.
    ``observed=false`` when no code graph or feature-clustering run exists.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    row = (
        await session.execute(select(CodeGraph).where(CodeGraph.project_id == project.id))  # ty: ignore[invalid-argument-type]
    ).scalar_one_or_none()
    if row is None:
        return FeatureFunctionGraphOut(observed=False)

    # Resolve the feature's files from the latest COMPLETED feature_clustering run.
    fc_run = (
        await session.execute(
            select(AnalysisRun)
            .where(
                col(AnalysisRun.project_id) == project.id,
                col(AnalysisRun.kind) == JobType.FEATURE_CLUSTERING.value,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if fc_run is None:
        return FeatureFunctionGraphOut(observed=False)
    feature = (
        await session.execute(select(Feature).where(col(Feature.run_id) == fc_run.id, col(Feature.key) == key))
    ).scalar_one_or_none()
    if feature is None:
        return FeatureFunctionGraphOut(observed=False)
    ff_rows = (
        (await session.execute(select(FeatureFile).where(col(FeatureFile.feature_id) == feature.id))).scalars().all()
    )
    fileset = {ff.file_path for ff in ff_rows}
    if not fileset:
        return FeatureFunctionGraphOut(observed=True, nodes=[], edges=[])

    graph = row.graph or {}
    # Functions in the feature's files, grouped by file. Composite ids avoid same-name collisions.
    fn_by_file: dict[str, list[str]] = {}
    for fn in graph.get("functions", []):
        f, name = fn.get("file"), fn.get("name")
        if f in fileset and name:
            fn_by_file.setdefault(f, []).append(name)

    # CALLS edges within the feature's files (intra- and cross-file).
    calls: list[tuple[str, str, str, str]] = []
    for c in graph.get("function_calls", []):
        sf, tf = _call_files(c)
        s, t = c.get("source"), c.get("target")
        if sf in fileset and tf in fileset and s and t:
            calls.append((sf, s, tf, t))

    # Node cap: keep files with the most functions first (they anchor the densest clusters), so a huge
    # feature degrades gracefully rather than silently dropping arbitrary nodes.
    truncated = False
    total_fn = sum(len(v) for v in fn_by_file.values())
    if total_fn + len(fn_by_file) > _MAX_FEATURE_NODES:
        truncated = True
        budget = _MAX_FEATURE_NODES
        kept: dict[str, list[str]] = {}
        for f, names in sorted(fn_by_file.items(), key=lambda kv: len(kv[1]), reverse=True):
            if budget <= 1:
                break
            take = names[: max(1, budget - 1)]  # reserve 1 for the file hub node
            kept[f] = take
            budget -= len(take) + 1
        fn_by_file = kept

    def _fn_id(file: str, name: str) -> str:
        return f"{file}::{name}"

    def _file_id(file: str) -> str:
        return f"file::{file}"

    kept_fns = {(f, n) for f, names in fn_by_file.items() for n in names}
    nodes: list[dict] = []
    for f, names in fn_by_file.items():
        nodes.append({"id": _file_id(f), "label": f.rsplit("/", 1)[-1], "file": f, "kind": "file"})
        for n in names:
            nodes.append({"id": _fn_id(f, n), "label": n, "file": f, "kind": "function"})

    edges: list[dict] = []
    for f, names in fn_by_file.items():  # CONTAINS: file hub → its functions
        for n in names:
            edges.append({"source": _file_id(f), "target": _fn_id(f, n), "type": "contains"})
    seen_calls: set[tuple[str, str]] = set()
    for sf, s, tf, t in calls:  # CALLS: function → function (both kept)
        if (sf, s) not in kept_fns or (tf, t) not in kept_fns:
            continue
        src_id, tgt_id = _fn_id(sf, s), _fn_id(tf, t)
        if src_id == tgt_id or (src_id, tgt_id) in seen_calls:
            continue
        seen_calls.add((src_id, tgt_id))
        edges.append({"source": src_id, "target": tgt_id, "type": "calls"})

    return FeatureFunctionGraphOut(observed=True, nodes=nodes, edges=edges, truncated=truncated)
