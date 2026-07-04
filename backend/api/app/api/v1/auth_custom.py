
"""Custom auth handlers that know about the refresh-token row.

Replaces fastapi-users' bundled /login + /logout for this app:
- /login writes cookies via both backends (access JWT + refresh DB-row).
- /refresh rotates with reuse detection.
- /logout revokes the refresh row and bumps `users.token_epoch` (subsequent step).
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Tuple, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import «REDACTED»
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

from app.core.access_token import «REDACTED»
from app.core.config import settings
from app.core.db import «REDACTED»
from app.core.refresh_strategy import «REDACTED»
from app.core.security import (
    UserManager,
    access_backend,
    «REDACTED»,
    «REDACTED»,
    «REDACTED»,
    get_user_manager,
    refresh_backend,
    «REDACTED»,
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
    credentials: «REDACTED» Depends()],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    access_strategy: Annotated[«REDACTED», Depends(«REDACTED»)],
    refresh_strategy: Annotated[«REDACTED», Depends(«REDACTED»)],
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


async def _get_and_lock_refresh_token(
    session: SAAsyncSession, token_value: str
) -> Optional[RefreshToken]:
    """Retrieve and lock a refresh token."""
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token == token_value).with_for_update()  # ty: ignore[«REDACTED»]
    )
    return result.scalar_one_or_none()


async def _handle_expired_or_revoked_token(
    old_token: RefreshToken, now: datetime
) -> Optional[str]:
    """Check if token is expired or revoked. Returns family_id if reuse detected."""
    if old_token.revoked_at is not None or old_token.expires_at < now:
        return old_token.family_id
    return None


async def _rotate_token_and_create_new_one(
    session: SAAsyncSession, old_token: RefreshToken, now: datetime
) -> str:
    """Rotate the old token and create a new one within the same family."""
    family_id = old_token.family_id
    user_id = old_token.user_id
    new_token_value = secrets.token_urlsafe(settings.«REDACTED»)

    session.add(
        RefreshToken(
            token=new_token_value,
            user_id=user_id,
            family_id=family_id,
            expires_at=now + timedelta(seconds=settings.«REDACTED»),
        )
    )
    old_token.revoked_at = now
    old_token.replaced_by_token = new_token_value
    return new_token_value


async def _handle_reuse_family_revocation(
    session: SAAsyncSession, reuse_family_id: str, now: datetime
) -> None:
    """Revoke all tokens in a detected reuse family."""
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == reuse_family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


@router.post("/refresh", status_code=204)
async def refresh(
    request: Request,
    session: Annotated[SAAsyncSession, Depends(«REDACTED»)],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    access_strategy: Annotated[«REDACTED», Depends(«REDACTED»)],
    refresh_strategy: Annotated[«REDACTED», Depends(«REDACTED»)],
) -> Response:
    """Rotate the refresh token. On reuse (revoked jti replayed), revoke the entire family.

    Runs the rotation as a single transaction with `SELECT ... FOR UPDATE` on the
    incoming token's row. The `refresh_strategy` dep is kept in the signature to keep
    the FastAPI dependency graph consistent with `/login`, but rotation writes go
    through the session directly so that reuse-detection, row-update, and new-row
    insert are atomic.
    """
    token_value = «REDACTED»
    if not token_value:
        raise HTTPException(status_code=401, detail="authentication_required")

    now = datetime.now(UTC)
    new_token_value: Optional[str] = None
    user_id: Optional[int] = None
    reuse_family_id: Optional[str] = None

    async with session.begin():
        old_token = await _get_and_lock_refresh_token(session, token_value)

        if old_token is None:
            raise HTTPException(status_code=401, detail="authentication_required")

        reuse_family_id = await _handle_expired_or_revoked_token(old_token, now)
        if reuse_family_id:
            # If reuse detected, the transaction for locking `old_token` must commit
            # before we can start a new one to revoke the family without rolling back.
            # The HTTPException will be raised after this block.
            pass
        else:
            new_token_value = await _rotate_token_and_create_new_one(session, old_token, now)
            user_id = old_token.user_id

    if reuse_family_id:
        async with session.begin():
            await _handle_reuse_family_revocation(session, reuse_family_id, now)
        raise HTTPException(status_code=401, detail="authentication_required")

    # If we reach here, new_token_value and user_id must have been set.
    if new_token_value is None or user_id is None:
        # This case should ideally not be reached if logic is correct, but for type safety.
        raise HTTPException(status_code=500, detail="Internal server error during token rotation")

    user = await user_manager.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication_required") # User not found should also be treated as auth required

    access_resp = await access_backend.login(access_strategy, user)
    refresh_resp = await «REDACTED».get_login_response(new_token_value)
    merged = Response(status_code=204)
    _merge_set_cookies(merged, access_resp, refresh_resp)
    return merged


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    session: Annotated[SAAsyncSession, Depends(«REDACTED»)],
) -> Response:
    """Revoke the current refresh-token row, bump `users.token_epoch`, clear both cookies.

    Idempotent: returns 204 even if no cookies are present. The epoch bump
    invalidates any still-valid access JWTs for the user (ASVS 3.3.1),
    closing the post-logout window where a stale cookie would otherwise work.
    """
    token_value = «REDACTED»
    if token_value:
        now = datetime.now(UTC)
        async with session.begin():
            old_token = await _get_and_lock_refresh_token(session, token_value)
            if old_token is not None and old_token.revoked_at is None:
                old_token.revoked_at = now
                await session.execute(
                    update(User).where(User.id == old_token.user_id).values(token_epoch=«REDACTED»  # ty: ignore[«REDACTED»]
                )

    access_logout = await «REDACTED».get_logout_response()
    refresh_logout = await «REDACTED».get_logout_response()
    merged = Response(status_code=204)
    _merge_set_cookies(merged, access_logout, refresh_logout)
    return merged
