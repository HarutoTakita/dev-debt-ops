"""Galaxy personal-KC aggregation (issue 032).

Reads issue 029's latest ``kc_analysis`` run (``file_kc`` + ``dependencies``) and folds it into the
personal galaxy: per-file the developer's KC(file,dev) and mastery, grouped into module star-systems,
plus the dependency wormholes. Read-only; ``observed=false`` (empty) when no KC run exists.

The KC formula / mastery thresholds are owned by issue 029 — this only projects the persisted rows.
"""

import posixpath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.project import Project
from app.models.user import User
from app.schemas.galaxy import FileMasteryOut, PersonalGalaxyOut, StarSystemOut, WormholeOut
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Dependency, FileKc


def _module_of(path: str) -> str:
    return posixpath.dirname(path) or "(root)"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def build_galaxy(session: AsyncSession, project: Project, user: User) -> PersonalGalaxyOut:
    """Project the latest kc_analysis run into the personal galaxy for ``user`` (empty if no run)."""
    fallback_dev = user.email or "you"
    kc_run = (
        await session.execute(
            select(AnalysisRun)
            .where(
                col(AnalysisRun.project_id) == project.id,
                col(AnalysisRun.kind) == JobType.KC_ANALYSIS.value,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if kc_run is None:
        return PersonalGalaxyOut(developer=fallback_dev, org_kc=0.0, observed=False, systems=[], wormholes=[])

    rows = (await session.execute(select(FileKc).where(col(FileKc.run_id) == kc_run.id))).scalars().all()
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

    by_module: dict[str, list[FileMasteryOut]] = {}
    all_kc: list[float] = []
    for path in sorted(agg_files):
        dev_row = dev_map.get(path)
        kc = dev_row.kc if dev_row is not None else 0.0
        mastery = dev_row.mastery if dev_row is not None else "unexplored"
        all_kc.append(kc)
        module = _module_of(path)
        by_module.setdefault(module, []).append(
            FileMasteryOut(path=path, module=module, kc=kc, mastery=mastery, mastered=mastery == "star")
        )

    systems = [
        StarSystemOut(module=module, kc=_mean([f.kc for f in files]), files=files)
        for module, files in sorted(by_module.items())
    ]

    dep_rows = (await session.execute(select(Dependency).where(col(Dependency.run_id) == kc_run.id))).scalars().all()
    wormholes = [WormholeOut.model_validate({"from": d.from_path, "to": d.to_path}) for d in dep_rows]

    return PersonalGalaxyOut(
        developer=developer,
        org_kc=_mean(all_kc),
        observed=True,
        systems=systems,
        wormholes=wormholes,
    )
