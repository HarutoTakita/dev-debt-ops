"""Thin extension of fastapi-users' SQLAlchemyAccessTokenDatabase for refresh rotation.

Adds two operations the base class doesn't provide:
- `get_by_token_locked` — `SELECT ... FOR UPDATE` on the row, closing the
  rotate-vs-replay race under concurrent `/refresh`.
- `revoke_family` — bulk revocation for reuse-detection.
"""

from datetime import UTC, datetime

from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy import select, update

from app.models.refresh_token import RefreshToken


class RefreshTokenDatabase(SQLAlchemyAccessTokenDatabase[RefreshToken]):
    """RefreshToken-specific db operations on top of the fastapi-users adapter."""

    async def get_by_token_locked(self, token: str) -> RefreshToken | None:
        """Return the row for `token` with `FOR UPDATE` so concurrent rotators block."""
        statement = (
            select(self.access_token_table)
            .where(self.access_token_table.token == token)  # ty: ignore[invalid-argument-type]
            .with_for_update()
        )
        results = await self.session.execute(statement)
        return results.scalar_one_or_none()

    async def revoke_family(self, family_id: str) -> None:
        """Revoke every non-revoked row in a rotation family."""
        now = datetime.now(UTC)
        await self.session.execute(
            update(self.access_token_table)
            .where(
                self.access_token_table.family_id == family_id,
                self.access_token_table.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.session.commit()
