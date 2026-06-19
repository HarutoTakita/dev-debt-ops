"""Delete refresh-token rows with `expires_at` older than 30 days.

Intended cadence: daily. Cron wiring is ops-runbook territory; see
`docs/reference/deployment.md` "定期メンテナンス: refresh token の刈り取り".

Usage:
    uv run python -m app.scripts.prune_refresh_tokens
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.db import sa_async_session_maker
from app.models.refresh_token import RefreshToken


async def _prune() -> int:
    """Delete rows with `expires_at < now() - 30 days` and return the count."""
    cutoff = datetime.now(UTC) - timedelta(days=30)
    async with sa_async_session_maker() as session, session.begin():
        result = await session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < cutoff).returning(RefreshToken.token)  # ty: ignore[no-matching-overload]
        )
        return len(result.all())


def main() -> None:
    """CLI entry point."""
    deleted = asyncio.run(_prune())
    print(f"pruned {deleted} expired refresh tokens")


if __name__ == "__main__":
    main()
