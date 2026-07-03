"""Startup demo-refresh guard: reseed only when DEMO_SEED_VERSION changed (DEMO_MODE_ENABLED only).

Verifies the guard is a no-op when demo mode is off, seeds once when enabled, is idempotent on a
second call at the same version, and reseeds again after the content version is bumped.
"""

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import db as app_db
from app.core.config import settings
from app.scripts import seed_demo
from app.scripts.seed_demo import _SEED_VERSION_KEY, refresh_demo_if_stale
from shared.models import QuizSession


async def _demo_quiz_count(session: AsyncSession, project_id) -> int:
    rows = (await session.exec(select(QuizSession).where(col(QuizSession.project_id) == project_id))).all()
    return len(rows)


async def test_refresh_noop_when_demo_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE_ENABLED", False)
    assert await refresh_demo_if_stale() is False


async def test_refresh_seeds_then_is_version_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE_ENABLED", True)
    monkeypatch.setattr(seed_demo, "DEMO_SEED_VERSION", "test-v1")

    # 1st call: version differs (marker absent) → reseeds.
    assert await refresh_demo_if_stale() is True

    project_id = seed_demo._u("project", seed_demo.DEMO_ORG_SLUG, seed_demo.DEMO_PROJECT_SLUG)
    async with app_db.async_session_maker() as s:
        count_after_first = await _demo_quiz_count(s, project_id)
        marker = await s.get(seed_demo.AppMetadata, _SEED_VERSION_KEY)
    assert count_after_first > 0
    assert marker is not None
    assert marker.value == "test-v1"

    # 2nd call at the same version → no-op, counts unchanged (idempotent).
    assert await refresh_demo_if_stale() is False
    async with app_db.async_session_maker() as s:
        assert await _demo_quiz_count(s, project_id) == count_after_first

    # Bump the content version → reseeds again (reset + seed), still populated & stable.
    monkeypatch.setattr(seed_demo, "DEMO_SEED_VERSION", "test-v2")
    assert await refresh_demo_if_stale() is True
    async with app_db.async_session_maker() as s:
        assert await _demo_quiz_count(s, project_id) == count_after_first
