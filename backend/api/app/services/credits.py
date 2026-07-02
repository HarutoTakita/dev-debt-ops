"""Per-user analysis credits (issue 298).

Bounds Gemini cost for the public hackathon: a repository-analysis run consumes one credit from the
triggering user, and repayment-PR creation requires a positive balance. Credits start at 0 and are
topped up by an admin (superuser). Gating is a no-op unless ``ANALYSIS_CREDITS_ENABLED`` is set, and
superusers always bypass — so dev/stg behave as before. Guest-demo users never reach these paths
(the GitHub chokepoint in ``api/v1/github.py`` already returns 403).
"""

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.models.user import User

_EXHAUSTED_DETAIL = {
    "reason": "credits_exhausted",
    "message": "解析クレジットが不足しています。管理者にクレジットの付与を依頼してください。",
}


def _bypass(user: User) -> bool:
    """Credits are only enforced when enabled and the user is not a superuser."""
    return not settings.ANALYSIS_CREDITS_ENABLED or bool(user.is_superuser)


async def consume_analysis_credit(session: AsyncSession, user: User) -> None:
    """Atomically consume one analysis credit, or raise 402 if the balance is exhausted.

    The decrement is a single guarded ``UPDATE ... WHERE analysis_credits > 0`` so concurrent runs by
    the same user cannot double-spend (Postgres row-locks serialize them). Runs in the request session
    so the decrement commits atomically with the enqueued Job (no refund on later failure — issue 298).
    """
    if _bypass(user):
        return
    stmt = (
        update(User)
        .where(col(User.id) == user.id, col(User.analysis_credits) > 0)
        .values(analysis_credits=col(User.analysis_credits) - 1)
        .returning(col(User.analysis_credits))
    )
    remaining = (await session.execute(stmt)).scalar_one_or_none()
    if remaining is None:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=_EXHAUSTED_DETAIL)
    user.analysis_credits = remaining  # keep the in-memory user consistent for the response


async def assert_has_credit(user: User) -> None:
    """Require a positive balance without consuming (repayment-PR gate). Raises 402 when exhausted."""
    if _bypass(user):
        return
    if user.analysis_credits <= 0:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=_EXHAUSTED_DETAIL)
