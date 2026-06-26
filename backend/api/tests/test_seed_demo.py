"""Idempotency tests for the guest-demo seed script (issue 069).

Seeding twice must not duplicate rows. We seed via ``seed()`` (the public entry point) twice and
assert the demo project's analysis row counts are stable across runs and non-empty, so the guest's
main screens (debt registry, KC galaxy, quiz) stay populated and re-runs are safe.
"""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import db as app_db
from app.scripts.seed_demo import seed
from shared.models import AnalysisRun, CodeDebt, FileKc, KnowledgeDebt, QuizSession


async def _count_by_project(session: AsyncSession, model, project_id) -> int:
    """Return the number of ``model`` rows scoped to ``project_id``."""
    rows = (await session.exec(select(model).where(col(model.project_id) == project_id))).all()
    return len(rows)


async def _count_file_kc(session: AsyncSession, project_id) -> int:
    """Return the number of ``FileKc`` rows for the project's analysis runs (FileKc has no project_id)."""
    run_ids = (await session.exec(select(AnalysisRun.id).where(col(AnalysisRun.project_id) == project_id))).all()
    if not run_ids:
        return 0
    rows = (await session.exec(select(FileKc).where(col(FileKc.run_id).in_(run_ids)))).all()
    return len(rows)


async def test_seed_demo_is_idempotent() -> None:
    """Seeding twice yields identical, non-zero counts for the demo project's analysis rows."""
    async with app_db.async_session_maker() as session:
        project = await seed(session)
    async with app_db.async_session_maker() as session:
        again = await seed(session)
    assert project.id == again.id  # same deterministic demo project

    async with app_db.async_session_maker() as session:
        code = await _count_by_project(session, CodeDebt, project.id)
        knowledge = await _count_by_project(session, KnowledgeDebt, project.id)
        quizzes = await _count_by_project(session, QuizSession, project.id)
        file_kc = await _count_file_kc(session, project.id)

    # All four populated screens are non-empty after two seeds...
    assert code > 0
    assert knowledge > 0
    assert quizzes > 0
    assert file_kc > 0

    # ...and a third seed did not duplicate rows.
    async with app_db.async_session_maker() as session:
        await seed(session)
    async with app_db.async_session_maker() as session:
        assert await _count_by_project(session, CodeDebt, project.id) == code
        assert await _count_by_project(session, KnowledgeDebt, project.id) == knowledge
        assert await _count_by_project(session, QuizSession, project.id) == quizzes
        assert await _count_file_kc(session, project.id) == file_kc
