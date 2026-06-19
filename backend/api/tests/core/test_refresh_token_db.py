from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.core import db as app_db
from app.core.refresh_token_db import RefreshTokenDatabase
from app.models.refresh_token import RefreshToken
from app.models.user import User


def _row(token: str, user_id, family_id: str, lifetime_days: int = 7) -> dict:
    return {
        "token": token,
        "user_id": user_id,
        "family_id": family_id,
        "expires_at": datetime.now(UTC) + timedelta(days=lifetime_days),
    }


async def test_revoke_family_revokes_only_non_revoked_rows_in_family(authenticated_client: AsyncClient) -> None:
    """revoke_family marks every active row in the family as revoked; other families untouched."""
    async with app_db.sa_async_session_maker() as session:
        user = (await session.execute(select(User))).scalars().first()
        assert user is not None
        db = RefreshTokenDatabase(session, RefreshToken)
        await db.create(_row("t1", user.id, "fam1"))
        await db.create(_row("t2", user.id, "fam1"))
        await db.create(_row("t3", user.id, "other"))

        await db.revoke_family("fam1")

        t1 = await db.get_by_token("t1")
        t2 = await db.get_by_token("t2")
        t3 = await db.get_by_token("t3")
        assert t1 is not None
        assert t1.revoked_at is not None
        assert t2 is not None
        assert t2.revoked_at is not None
        assert t3 is not None
        assert t3.revoked_at is None


async def test_get_by_token_locked_returns_row_or_none(authenticated_client: AsyncClient) -> None:
    """Smoke-test: FOR UPDATE variant returns the row when present, None otherwise.

    Concurrency semantics are verified end-to-end in the /refresh rotation test.
    """
    async with app_db.sa_async_session_maker() as session:
        user = (await session.execute(select(User))).scalars().first()
        assert user is not None
        db = RefreshTokenDatabase(session, RefreshToken)
        await db.create(_row("locked-one", user.id, "f"))

        async with app_db.sa_async_session_maker() as read_session, read_session.begin():
            db2 = RefreshTokenDatabase(read_session, RefreshToken)
            row = await db2.get_by_token_locked("locked-one")
            assert row is not None
            assert row.token == "locked-one"
            missing = await db2.get_by_token_locked("no-such-token")
            assert missing is None
