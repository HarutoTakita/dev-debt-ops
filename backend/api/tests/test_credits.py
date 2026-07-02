"""issue 298: per-user analysis credits (consume / assert / bypass)."""

import uuid

import pytest
from fastapi import HTTPException

from app.core import db as app_db
from app.core.config import settings
from app.models.user import User
from app.services.credits import assert_has_credit, consume_analysis_credit


@pytest.fixture
def credits_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANALYSIS_CREDITS_ENABLED", True)


async def _make_user(*, credits: int, is_superuser: bool = False) -> uuid.UUID:
    async with app_db.async_session_maker() as session:
        user = User(
            email=f"u-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=is_superuser,
            is_verified=True,
            analysis_credits=credits,
        )
        session.add(user)
        await session.commit()
        return user.id


async def _reload(user_id: uuid.UUID) -> User:
    async with app_db.async_session_maker() as session:
        return await session.get(User, user_id)


async def test_consume_decrements_then_raises_when_exhausted(credits_enabled: None) -> None:
    uid = await _make_user(credits=1)
    async with app_db.async_session_maker() as session:
        user = await session.get(User, uid)
        await consume_analysis_credit(session, user)  # 1 → 0
        await session.commit()
        assert user.analysis_credits == 0

    async with app_db.async_session_maker() as session:
        user = await session.get(User, uid)
        with pytest.raises(HTTPException) as exc:
            await consume_analysis_credit(session, user)  # 0 → 402
        assert exc.value.status_code == 402
        assert exc.value.detail["reason"] == "credits_exhausted"
    assert (await _reload(uid)).analysis_credits == 0  # not driven negative


async def test_consume_bypasses_when_disabled() -> None:
    """Flag off (default) → no decrement, no error even at 0 balance (dev/stg behave as before)."""
    uid = await _make_user(credits=0)
    async with app_db.async_session_maker() as session:
        user = await session.get(User, uid)
        await consume_analysis_credit(session, user)  # no raise
        await session.commit()
    assert (await _reload(uid)).analysis_credits == 0


async def test_consume_bypasses_for_superuser(credits_enabled: None) -> None:
    uid = await _make_user(credits=0, is_superuser=True)
    async with app_db.async_session_maker() as session:
        user = await session.get(User, uid)
        await consume_analysis_credit(session, user)  # superuser bypass, no raise
        await session.commit()
    assert (await _reload(uid)).analysis_credits == 0


async def test_assert_has_credit_gate(credits_enabled: None) -> None:
    zero = await _reload(await _make_user(credits=0))
    with pytest.raises(HTTPException) as exc:
        await assert_has_credit(zero)
    assert exc.value.status_code == 402

    positive = await _reload(await _make_user(credits=2))
    await assert_has_credit(positive)  # no raise (balance > 0, not consumed)
    assert positive.analysis_credits == 2


async def test_assert_has_credit_bypasses_when_disabled() -> None:
    zero = await _reload(await _make_user(credits=0))
    await assert_has_credit(zero)  # flag off → no raise
