import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import case, func, or_
from sqlmodel import col, select

from app.api.deps import CurrentSuperuser, CurrentUser, SessionDep
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import fastapi_users
from app.models.user import User
from app.schemas.user import UserActivityOut, UserCreditsGrant, UserRead, UserRoleUpdate, UserUpdate
from app.services.demo_members import demo_member_activity
from shared.enums import JobType
from shared.models import CodeDebt, Job, LearningPlan, LearningStep, QuizSession

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
    # `User.oauth_accounts` は lazy="joined"（コレクションの joined eager load）のため、
    # 重複行を畳む unique() が必須（未呼び出しだと InvalidRequestError）。
    return list(result.unique().all())


@router.get(
    "/activity",
    response_model=list[UserActivityOut],
    summary="List members with operational activity",
    response_description="Per-member activity for the admin dashboard (learning / quiz / PR / issue / last active).",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Caller is not a superuser."},
    },
)
async def list_user_activity(
    current_user: CurrentUser,
    session: SessionDep,
    q: str | None = Query(
        default=None,
        description="Substring filter applied case-insensitively to email and display_name.",
    ),
    limit: int = Query(default=200, le=500, description="Maximum number of members to return (capped at 500)."),
    offset: int = Query(default=0, ge=0, description="Number of members to skip before returning results."),
) -> list[UserActivityOut]:
    """Return members with their aggregated activity across all projects.

    Superusers get the real aggregation; the guest-demo user gets fabricated sample members (so the
    admin dashboard is demoable without exposing any real account). Everyone else is forbidden.

    Aggregates are computed with a handful of grouped queries (one per metric family) rather than
    per-user loops, then joined in Python — so the response stays O(1) queries regardless of member
    count. Metrics: learning-plan step progress, quiz completion + average score, repayment-PR and
    GitHub-issue creation counts, and last activity.
    """
    if not (current_user.is_superuser or current_user.is_demo):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理者のみ利用できます。")

    # Guest demo: serve fabricated sample members (never real user data), then apply q / pagination.
    if current_user.is_demo:
        members = demo_member_activity()
        if q:
            needle = q.lower()
            members = [
                mmb for mmb in members if needle in mmb.email.lower() or needle in (mmb.display_name or "").lower()
            ]
        return members[offset : offset + limit]

    # 1) Members (same filter/pagination as list_users). oauth_accounts joined-eager → unique().
    stmt = select(User).where(User.deleted_at.is_(None))
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(pattern), func.lower(User.display_name).like(pattern)))
    stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
    users = list((await session.exec(stmt)).unique().all())
    ids = [u.id for u in users]
    if not ids:
        return []

    # 2) Learning: plan count + step totals/completed, grouped by owner (developer_id = users.id).
    plans_q = (
        select(LearningPlan.developer_id, func.count(col(LearningPlan.id)))
        .where(col(LearningPlan.developer_id).in_(ids))
        .group_by(col(LearningPlan.developer_id))
    )
    plans_count = {dev: int(n) for dev, n in (await session.exec(plans_q)).all()}

    steps_q = (
        select(
            LearningPlan.developer_id,
            func.count(col(LearningStep.id)),
            func.coalesce(func.sum(case((col(LearningStep.completed), 1), else_=0)), 0),
        )
        .join(LearningStep, col(LearningStep.plan_id) == col(LearningPlan.id))
        .where(col(LearningPlan.developer_id).in_(ids))
        .group_by(col(LearningPlan.developer_id))
    )
    steps_by_user = {dev: (int(total), int(done)) for dev, total, done in (await session.exec(steps_q)).all()}

    # 3) Quiz: total sessions, completed count, and average score over completed (0–1 fraction).
    quiz_q = (
        select(
            QuizSession.developer_id,
            func.count(col(QuizSession.id)),
            func.coalesce(func.sum(case((col(QuizSession.status) == "completed", 1), else_=0)), 0),
            func.avg(case((col(QuizSession.status) == "completed", col(QuizSession.score)))),
        )
        .where(col(QuizSession.developer_id).in_(ids))
        .group_by(col(QuizSession.developer_id))
    )
    quiz_by_user = {
        dev: (int(total), int(done), float(avg) if avg is not None else None)
        for dev, total, done, avg in (await session.exec(quiz_q)).all()
    }

    # 4) Code-quality engagement: repayment-PR jobs + issues created, attributed to the acting user.
    pr_q = (
        select(Job.created_by, func.count(col(Job.id)))
        .where(col(Job.job_type) == JobType.REPAYMENT_PR_GENERATION, col(Job.created_by).in_(ids))
        .group_by(col(Job.created_by))
    )
    pr_count = {dev: int(n) for dev, n in (await session.exec(pr_q)).all()}

    issue_q = (
        select(CodeDebt.related_issue_by, func.count(col(CodeDebt.id)))
        .where(col(CodeDebt.related_issue_by).in_(ids))
        .group_by(col(CodeDebt.related_issue_by))
    )
    issue_count = {dev: int(n) for dev, n in (await session.exec(issue_q)).all()}

    out: list[UserActivityOut] = []
    for u in users:
        steps_total, steps_done = steps_by_user.get(u.id, (0, 0))
        quiz_total, quiz_done, quiz_avg = quiz_by_user.get(u.id, (0, 0, None))
        out.append(
            UserActivityOut(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                is_superuser=u.is_superuser,
                is_demo=u.is_demo,
                last_active_at=u.last_active_at,
                created_at=u.created_at,
                analysis_credits=u.analysis_credits,
                learning_plans_count=plans_count.get(u.id, 0),
                learning_steps_total=steps_total,
                learning_steps_completed=steps_done,
                quiz_total=quiz_total,
                quiz_completed=quiz_done,
                quiz_avg_score=quiz_avg,
                pr_count=pr_count.get(u.id, 0),
                issue_count=issue_count.get(u.id, 0),
            )
        )
    return out


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
