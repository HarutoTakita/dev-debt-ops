"""Guest demo login (issue 069) — GitHub-less, mounted only when ``DEMO_MODE_ENABLED``.

Mirrors ``auth_custom.login()`` cookie issuance but skips credential authentication: it
resolves the shared demo user (``ensure_demo_user``) and writes the same access (JWT) +
refresh (DB-row) cookies, so the rest of the app treats the guest like any logged-in user
(while ``is_demo`` gates GitHub/write actions).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

from app.api.v1.auth_custom import _merge_set_cookies
from app.core.access_token import EpochCheckedJWTStrategy
from app.core.db import get_sa_async_session
from app.core.refresh_strategy import RefreshDatabaseStrategy
from app.core.security import (
    UserManager,
    access_backend,
    get_access_jwt_strategy,
    get_refresh_db_strategy,
    get_user_manager,
    refresh_backend,
)
from app.services.demo import ensure_demo_user

router = APIRouter()


@router.post("/demo", status_code=204)
async def demo_login(
    request: Request,
    session: Annotated[SAAsyncSession, Depends(get_sa_async_session)],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    access_strategy: Annotated[EpochCheckedJWTStrategy, Depends(get_access_jwt_strategy)],
    refresh_strategy: Annotated[RefreshDatabaseStrategy, Depends(get_refresh_db_strategy)],
) -> Response:
    """Log in as the shared read-only guest-demo user (no GitHub, no credentials).

    Sets access + refresh cookies exactly like ``/login``. Only mounted when
    ``settings.DEMO_MODE_ENABLED`` is true (see ``auth.py``).
    """
    user = await ensure_demo_user(session)
    access_resp = await access_backend.login(access_strategy, user)
    refresh_resp = await refresh_backend.login(refresh_strategy, user)
    merged = Response(status_code=204)
    _merge_set_cookies(merged, access_resp, refresh_resp)
    await user_manager.on_after_login(user, request, merged)
    return merged
