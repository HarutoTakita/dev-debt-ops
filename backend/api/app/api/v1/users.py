import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, status
from sqlalchemy import func, or_
from sqlmodel import select

from app.api.deps import CurrentSuperuser, SessionDep
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import fastapi_users
from app.models.user import User
from app.schemas.user import UserCreditsGrant, UserRead, UserRoleUpdate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=list[UserRead],
    summary="List users",
    response_description="Paginated list of users (newest first, optionally filtered by email/display_name).",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Caller is not a superuser."},
    },
)
async def list_users(
    _admin: CurrentSuperuser,
    session: SessionDep,
    q: str | None = Query(
        default=None,
        description="Substring filter applied case-insensitively to email and display_name.",
    ),
    limit: int = Query(default=100, le=500, description="Maximum number of users to return (capped at 500)."),
    offset: int = Query(default=0, ge=0, description="Number of users to skip before returning results."),
) -> list[User]:
    """Return all users ordered by creation date, newest first.

    `q` performs a case-insensitive substring match against both `email` and
    `display_name` — rows matching either field are included. Use `limit` and
    `offset` for cursor-free pagination.
    """
    stmt = select(User).where(User.deleted_at.is_(None))
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(pattern), func.lower(User.display_name).like(pattern)))
    stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await session.exec(stmt)
    return list(result.all())


@router.patch(
    "/{user_id}/role",
    response_model=UserRead,
    summary="Promote or demote a user",
    response_description="Updated user record.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Superuser attempted to demote themselves."},
        status.HTTP_404_NOT_FOUND: {"description": "User not found."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Caller is not a superuser."},
    },
)
async def set_user_role(
    user_id: Annotated[uuid.UUID, Path(description="UUID of the user whose role is changing.")],
    body: UserRoleUpdate,
    admin: CurrentSuperuser,
    session: SessionDep,
) -> User:
    """Promote or demote a user between the `admin` and `user` roles.

    Sets `is_superuser` on the target user: `role='admin'` grants it,
    `role='user'` revokes it. A self-demotion guard prevents the calling
    superuser from removing their own admin privileges. The `role` field
    is validated server-side by Pydantic via `UserRoleUpdate`.

    Raises:
        NotFoundError: If no user with `user_id` exists.
        BadRequestError: If the calling superuser attempts to demote themselves.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    if user.id == admin.id and body.role != "admin":
        raise BadRequestError("cannot demote yourself")
    user.is_superuser = body.role == "admin"
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post(
    "/{user_id}/credits",
    response_model=UserRead,
    summary="Grant analysis credits to a user",
    response_description="Updated user record with the new balance.",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "User not found."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Caller is not a superuser."},
    },
)
async def grant_user_credits(
    user_id: Annotated[uuid.UUID, Path(description="UUID of the user receiving credits.")],
    body: UserCreditsGrant,
    _admin: CurrentSuperuser,
    session: SessionDep,
) -> User:
    """Add ``amount`` repository-analysis credits to a user's balance (superuser only, issue 298).

    This is the manual top-up path (a future admin screen will call it). Credits start at 0, so a
    user cannot run analysis until an admin grants some (when ``ANALYSIS_CREDITS_ENABLED``).

    Raises:
        NotFoundError: If no user with ``user_id`` exists.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    user.analysis_credits += body.amount
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate))
