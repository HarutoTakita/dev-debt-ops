"""Guest-demo helpers (issue 069): the shared read-only demo user.

The demo user has no GitHub OAuth account, is never a superuser, and is marked
``is_demo=True`` so the GitHub-client chokepoint (``api/v1/github.py``) returns 403 and the
frontend gates GitHub/write actions. ``ensure_demo_user`` is idempotent and shared by the
``POST /api/v1/auth/demo`` endpoint and the ``seed_demo`` script.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# Stable identity for the single shared demo account.
DEMO_USER_EMAIL = "demo@devdebtops.example"
DEMO_USER_DISPLAY_NAME = "ゲスト"


async def ensure_demo_user(session: AsyncSession) -> User:
    """Return the shared demo user, creating it on first use (idempotent).

    Created directly (not via the fastapi-users manager) so the personal-org
    ``on_after_register`` hook does not run — the demo org / project come from the
    ``seed_demo`` script instead. The account has an unusable password hash (password
    login can never succeed); it is only reachable via ``POST /api/v1/auth/demo``.
    """
    result = await session.execute(select(User).where(User.email == DEMO_USER_EMAIL))  # ty: ignore[invalid-argument-type]
    # User.oauth_accounts is a joined eager-load collection → must .unique() before scalar.
    user = result.unique().scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        id=uuid.uuid4(),
        email=DEMO_USER_EMAIL,
        hashed_password="!guest-demo-no-password-login",  # unusable; demo login never verifies a password
        is_active=True,
        is_superuser=False,
        is_verified=True,
        display_name=DEMO_USER_DISPLAY_NAME,
        is_demo=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
