"""Galaxy personal-KC aggregation (issue 032 + feature graph issue 065).

Reads issue 029's latest ``kc_analysis`` run (``file_kc`` + ``dependencies``) and folds it into the
personal galaxy: per-file the developer's KC(file,dev) and mastery, grouped into module star-systems,
plus the dependency wormholes. On top, projects the latest ``feature_clustering`` run (issue 052) into a
**feature graph**: feature nodes (aggregate KC) + feature→feature edges (file dependencies mapped through
``feature_files`` and kept only when they cross a feature boundary). Each file is tagged with its
``feature_keys`` so the frontend can draw a per-feature file subgraph on drill-down (issue 065).

Read-only; ``observed=false`` (empty) when no KC run exists. Feature fields are empty (frontend falls
back to the file/module view) when no feature_clustering run exists yet.
"""

import posixpath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.project import Project
from app.models.user import User
from app.schemas.galaxy import (
    FeatureEdgeOut,
    FeatureNodeOut,
    FileMasteryOut,
    PersonalGalaxyOut,
    StarSystemOut,
    WormholeOut,
)
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Dependency, Feature, FeatureFile, FileKc


def _module_of(path: str) -> str:
    return posixpath.dirname(path) or "(root)"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _mastery_of(kc: float) -> str:
    """Map an aggregate KC into a mastery tier (issue 029 thresholds; aggregate has no per-dev contact)."""
    if kc >= 0.7:
        return "star"
    if kc >= 0.4:
        return "dim_star"
    if kc > 0.0:
        return "black_hole"
    return "unexplored"


async def _latest_run_id(session: AsyncSession, project_id, kind: str):
    return (
        await session.execute(
            select(AnalysisRun.id)
            .where(
                col(AnalysisRun.project_id) == project_id,
                col(AnalysisRun.kind) == kind,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def build_galaxy(session: AsyncSession, project: Project, user: User) -> PersonalGalaxyOut:
    """Project the latest kc_analysis (+ feature_clustering) runs into the personal galaxy for ``user``."""
    fallback_dev = user.email or "you"
    kc_run_id = await _latest_run_id(session, project.id, JobType.KC_ANALYSIS.value)
    if kc_run_id is None:
        return PersonalGalaxyOut(developer=fallback_dev, org_kc=0.0, observed=False, systems=[], wormholes=[])

    rows = (await session.execute(select(FileKc).where(col(FileKc.run_id) == kc_run_id))).scalars().all()
    agg_files: list[str] = []  # file_path of aggregate rows = the file universe
    dev_map: dict[str, FileKc] = {}  # this developer's KC(file,dev) rows
    developer = fallback_dev
    for r in rows:
        if r.dev_id is None and r.github_handle is None:
            agg_files.append(r.file_path)
        elif r.dev_id == user.id:
            dev_map[r.file_path] = r
            if r.github_handle:
                developer = r.github_handle

    kc_by_file: dict[str, float] = {}
    mastery_by_file: dict[str, str] = {}
    for path in agg_files:
        dev_row = dev_map.get(path)
        kc_by_file[path] = dev_row.kc if dev_row is not None else 0.0
        mastery_by_file[path] = dev_row.mastery if dev_row is not None else "unexplored"

    # Feature mapping from the latest feature_clustering run (issue 052). Empty when none → file/module
    # view only (frontend falls back). A file may belong to multiple features (feature_files is many-to-many).
    fc_run_id = await _latest_run_id(session, project.id, JobType.FEATURE_CLUSTERING.value)
    feature_name: dict[str, str] = {}
    files_by_feature: dict[str, list[str]] = {}
    feature_keys_by_file: dict[str, list[str]] = {}
    if fc_run_id is not None:
        feats = (await session.execute(select(Feature).where(col(Feature.run_id) == fc_run_id))).scalars().all()
        id_to_key = {f.id: f.key for f in feats}
        for f in feats:
            feature_name[f.key] = f.name
            files_by_feature.setdefault(f.key, [])
        ffs = (await session.execute(select(FeatureFile).where(col(FeatureFile.run_id) == fc_run_id))).scalars().all()
        for ff in ffs:
            key = id_to_key.get(ff.feature_id)
            if key is None:
                continue
            files_by_feature.setdefault(key, []).append(ff.file_path)
            feature_keys_by_file.setdefault(ff.file_path, []).append(key)

    by_module: dict[str, list[FileMasteryOut]] = {}
    all_kc: list[float] = []
    for path in sorted(agg_files):
        kc = kc_by_file[path]
        mastery = mastery_by_file[path]
        all_kc.append(kc)
        module = _module_of(path)
        by_module.setdefault(module, []).append(
            FileMasteryOut(
                path=path,
                module=module,
                kc=kc,
                mastery=mastery,
                mastered=mastery == "star",
                feature_keys=feature_keys_by_file.get(path, []),
            )
        )

    systems = [
        StarSystemOut(module=module, kc=_mean([f.kc for f in files]), files=files)
        for module, files in sorted(by_module.items())
    ]

    # Feature nodes: aggregate the developer's KC over each feature's files (only files that have KC rows).
    features = [
        FeatureNodeOut(
            key=key,
            name=feature_name.get(key, key),
            kc=(feat_kc := _mean([kc_by_file[p] for p in files_by_feature[key] if p in kc_by_file])),
            mastery=_mastery_of(feat_kc),
            file_count=len(files_by_feature[key]),
        )
        for key in sorted(files_by_feature)
    ]

    dep_rows = (await session.execute(select(Dependency).where(col(Dependency.run_id) == kc_run_id))).scalars().all()
    wormholes = [WormholeOut.model_validate({"from": d.from_path, "to": d.to_path}) for d in dep_rows]

    # Feature→feature edges: map each file dependency to its features and keep cross-feature pairs (dedup).
    edge_seen: set[tuple[str, str]] = set()
    feature_edges: list[FeatureEdgeOut] = []
    for d in dep_rows:
        for a in feature_keys_by_file.get(d.from_path, []):
            for b in feature_keys_by_file.get(d.to_path, []):
                if a == b or (a, b) in edge_seen:
                    continue
                edge_seen.add((a, b))
                feature_edges.append(FeatureEdgeOut.model_validate({"from": a, "to": b}))

    return PersonalGalaxyOut(
        developer=developer,
        org_kc=_mean(all_kc),
        observed=True,
        systems=systems,
        wormholes=wormholes,
        features=features,
        feature_edges=feature_edges,
    )
