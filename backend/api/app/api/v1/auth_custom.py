"""Custom auth handlers that know about the refresh-token row.

Replaces fastapi-users' bundled /login + /logout for this app:
- /login writes cookies via both backends (access JWT + refresh DB-row).
- /refresh rotates with reuse detection.
- /logout revokes the refresh row and bumps `users.token_epoch` (subsequent step).
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

from app.core.access_token import EpochCheckedJWTStrategy
from app.core.config import settings
from app.core.db import get_sa_async_session
from app.core.refresh_strategy import RefreshDatabaseStrategy
from app.core.security import (
    UserManager,
    access_backend,
    access_cookie_transport,
    get_access_jwt_strategy,
    get_refresh_db_strategy,
    get_user_manager,
    refresh_backend,
    refresh_cookie_transport,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User

router = APIRouter()


def _merge_set_cookies(target: Response, *sources: Response) -> None:
    """Append every `set-cookie` header from sources onto `target` in order."""
    for src in sources:
        for key, value in src.headers.items():
            if key.lower() == "set-cookie":
                target.headers.append("set-cookie", value)


@router.post("/login", status_code=204)
async def login(
    request: Request,
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    access_strategy: Annotated[EpochCheckedJWTStrategy, Depends(get_access_jwt_strategy)],
    refresh_strategy: Annotated[RefreshDatabaseStrategy, Depends(get_refresh_db_strategy)],
) -> Response:
    """Authenticate credentials, set access + refresh cookies, fire on_after_login."""
    user = await user_manager.authenticate(credentials)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")
    access_resp = await access_backend.login(access_strategy, user)
    refresh_resp = await refresh_backend.login(refresh_strategy, user)

    merged = Response(status_code=204)
    _merge_set_cookies(merged, access_resp, refresh_resp)
    await user_manager.on_after_login(user, request, merged)
    return merged


@router.post("/refresh", status_code=204)
async def refresh(
    request: Request,
    session: Annotated[SAAsyncSession, Depends(get_sa_async_session)],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    access_strategy: Annotated[EpochCheckedJWTStrategy, Depends(get_access_jwt_strategy)],
    refresh_strategy: Annotated[RefreshDatabaseStrategy, Depends(get_refresh_db_strategy)],
) -> Response:
    """Rotate the refresh token. On reuse (revoked jti replayed), revoke the entire family.

    Runs the rotation as a single transaction with `SELECT ... FOR UPDATE` on the
    incoming token's row. The `refresh_strategy` dep is kept in the signature to keep
    the FastAPI dependency graph consistent with `/login`, but rotation writes go
    through the session directly so that reuse-detection, row-update, and new-row
    insert are atomic.
    """
    token_value = request.cookies.get(refresh_cookie_transport.cookie_name)
    if not token_value:
        raise HTTPException(status_code=401, detail="authentication_required")

    now = datetime.now(UTC)
    reuse_detected = False
    reuse_family: str | None = None

    async with session.begin():
        locked = await session.execute(
            select(RefreshToken).where(RefreshToken.token == token_value).with_for_update()  # ty: ignore[invalid-argument-type]
        )
        old = locked.scalar_one_or_none()
        if old is None:
            raise HTTPException(status_code=401, detail="authentication_required")
        if old.revoked_at is not None or old.expires_at < now:
            # Capture the family; revoke in a fresh transaction after this block
            # commits so the change isn't rolled back by the HTTPException below.
            reuse_detected = True
            reuse_family = old.family_id
        else:
            family_id = old.family_id
            user_id = old.user_id
            new_token = secrets.token_urlsafe(32)
            session.add(
                RefreshToken(
                    token=new_token,
                    user_id=user_id,
                    family_id=family_id,
                    expires_at=now + timedelta(seconds=settings.REFRESH_TOKEN_LIFETIME_SECONDS),
                )
            )
            old.revoked_at = now
            old.replaced_by_token = new_token

    if reuse_detected:
        async with session.begin():
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.family_id == reuse_family,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
        raise HTTPException(status_code=401, detail="authentication_required")

    user = await user_manager.get(user_id)
    access_resp = await access_backend.login(access_strategy, user)
    refresh_resp = await refresh_cookie_transport.get_login_response(new_token)
    merged = Response(status_code=204)
    _merge_set_cookies(merged, access_resp, refresh_resp)
    return merged


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    session: Annotated[SAAsyncSession, Depends(get_sa_async_session)],
) -> Response:
    """Revoke the current refresh-token row, bump `users.token_epoch`, clear both cookies.

    Idempotent: returns 204 even if no cookies are present. The epoch bump
    invalidates any still-valid access JWTs for the user (ASVS 3.3.1),
    closing the post-logout window where a stale cookie would otherwise work.
    """
    token_value = request.cookies.get(refresh_cookie_transport.cookie_name)
    if token_value:
        now = datetime.now(UTC)
        async with session.begin():
            locked = await session.execute(
                select(RefreshToken).where(RefreshToken.token == token_value).with_for_update()  # ty: ignore[invalid-argument-type]
            )
            old = locked.scalar_one_or_none()
            if old is not None and old.revoked_at is None:
                old.revoked_at = now
                await session.execute(
                    update(User).where(User.id == old.user_id).values(token_epoch=int(now.timestamp()))  # ty: ignore[invalid-argument-type]
                )

    access_logout = await access_cookie_transport.get_logout_response()
    refresh_logout = await refresh_cookie_transport.get_logout_response()
    merged = Response(status_code=204)
    _merge_set_cookies(merged, access_logout, refresh_logout)
    return merged
