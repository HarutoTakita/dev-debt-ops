"""prune_superseded_runs: 再解析で溜まる古い run と run スコープ行を掃除する（最新のみ残す）。"""

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select

from service.pipelines.run_cleanup import prune_superseded_runs
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, CodeDebt, FileKc


async def _run(session, project_id: uuid.UUID, kind: str) -> AnalysisRun:
    run = AnalysisRun(project_id=project_id, commit_sha="c", kind=kind, status=JobStatus.COMPLETED)
    session.add(run)
    await session.flush()
    return run


async def test_prune_keeps_latest_and_deletes_old_run_scoped_rows(session_maker: async_sessionmaker) -> None:
    project_id = uuid.uuid4()
    async with session_maker() as session:
        old = await _run(session, project_id, JobType.KC_ANALYSIS.value)
        new = await _run(session, project_id, JobType.KC_ANALYSIS.value)
        # 別プロジェクト / 別 kind は無関係（消さない）。
        other_kind = await _run(session, project_id, JobType.CODE_DEBT_DETECTION.value)
        other_project = await _run(session, uuid.uuid4(), JobType.KC_ANALYSIS.value)
        session.add_all(
            [
                FileKc(run_id=old.id, file_path="a.py", kc=0.5, mastery="dim_star"),
                FileKc(run_id=new.id, file_path="a.py", kc=0.6, mastery="dim_star"),
                CodeDebt(
                    run_id=other_kind.id,
                    project_id=project_id,
                    file_path="a.py",
                    type="complexity",
                    severity="high",
                    code_debt_score=0.7,
                ),
            ]
        )
        await session.commit()
        new_id, old_id, other_kind_id, other_project_id = new.id, old.id, other_kind.id, other_project.id

    async with session_maker() as session:
        pruned = await prune_superseded_runs(
            session, project_id=project_id, kind=JobType.KC_ANALYSIS.value, keep_run_id=new_id
        )
        await session.commit()
        assert pruned == 1  # only the older KC run

    async with session_maker() as session:
        run_ids = set((await session.execute(select(AnalysisRun.id))).scalars().all())
        assert old_id not in run_ids  # superseded KC run removed
        assert {new_id, other_kind_id, other_project_id} <= run_ids  # latest + other kind/project kept
        kc_run_ids = set((await session.execute(select(FileKc.run_id))).scalars().all())
        assert old_id not in kc_run_ids  # old run's file_kc gone
        assert new_id in kc_run_ids  # latest run's file_kc kept
