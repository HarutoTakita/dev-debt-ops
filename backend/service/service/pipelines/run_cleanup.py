"""Prune superseded analysis runs so re-analysis doesn't accumulate per-file rows across old runs.

Each analysis (a new ``Job``) creates a new ``AnalysisRun`` per kind. Reads use the *latest* COMPLETED
run, but old runs' run-scoped rows (``file_kc`` / ``features`` / ``code_debts`` / …) otherwise linger
forever — bloating the DB and making the same file appear registered many times (once per run). After a
pipeline marks its run COMPLETED it calls :func:`prune_superseded_runs` to delete the project's *older*
runs of the SAME kind and every row scoped to them. Idempotent and transactional (runs in the pipeline's
session; the caller's final commit persists it).
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from shared.enums import JobStatus
from shared.models import (
    AnalysisRun,
    AssignedDeveloper,
    CodeDebt,
    Dependency,
    Feature,
    FeatureFile,
    FileKc,
    KnowledgeDebt,
    RepoFile,
)

# ``run_id`` を持つ行スコープテーブル。feature_files は features より先に消す（feature_id の FK 順序）。
_RUN_SCOPED = (FileKc, RepoFile, Dependency, FeatureFile, Feature, CodeDebt, KnowledgeDebt)


async def prune_superseded_runs(
    session: AsyncSession, *, project_id: uuid.UUID, kind: str, keep_run_id: uuid.UUID
) -> int:
    """Delete the project's older ``kind`` runs (keeping ``keep_run_id``) and their run-scoped rows.

    Returns the number of pruned runs. No-op when there is nothing older to remove.
    """
    # COMPLETED のみ対象（並行解析中の in-flight= PROCESSING run は消さない）。
    old_run_ids = list(
        (
            await session.execute(
                select(col(AnalysisRun.id)).where(
                    col(AnalysisRun.project_id) == project_id,
                    col(AnalysisRun.kind) == kind,
                    col(AnalysisRun.status) == JobStatus.COMPLETED,
                    col(AnalysisRun.id) != keep_run_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not old_run_ids:
        return 0

    # assigned_developers は debt を判別カラム（FK 無し）で参照するため、対象 debt を集めて先に削除する。
    debt_ids = list(
        (await session.execute(select(col(CodeDebt.id)).where(col(CodeDebt.run_id).in_(old_run_ids)))).scalars().all()
    )
    debt_ids += list(
        (await session.execute(select(col(KnowledgeDebt.id)).where(col(KnowledgeDebt.run_id).in_(old_run_ids))))
        .scalars()
        .all()
    )
    if debt_ids:
        await session.execute(delete(AssignedDeveloper).where(col(AssignedDeveloper.debt_id).in_(debt_ids)))

    for model in _RUN_SCOPED:
        await session.execute(delete(model).where(col(model.run_id).in_(old_run_ids)))
    await session.execute(delete(AnalysisRun).where(col(AnalysisRun.id).in_(old_run_ids)))
    return len(old_run_ids)
