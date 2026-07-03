import uuid
from datetime import datetime
from typing import Literal

from fastapi_users import schemas
from pydantic import BaseModel, Field


class UserRead(schemas.BaseUser[uuid.UUID]):
    """User as exposed to API clients.

    Inherits `id`, `email`, `is_active`, `is_superuser`, and `is_verified` from
    `BaseUser`. Locally-added fields are `display_name`, `created_at`, and
    `last_active_at`.
    """

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")
    created_at: datetime | None = Field(
        default=None,
        description="Timestamp when the user account was created; nullable due to pre-migration rows.",
    )
    last_active_at: datetime | None = Field(
        default=None,
        description="Timestamp of the user's last authenticated activity; nullable due to pre-migration rows.",
    )
    is_demo: bool = Field(
        default=False,
        description="True for the shared guest-demo user (read-only, no GitHub); drives demo UI gating.",
    )
    analysis_credits: int = Field(
        default=0,
        description="Remaining repository-analysis credits (issue 298); drives the analysis/PR button gating.",
    )


class UserCreate(schemas.BaseUserCreate):
    """Body for user registration."""

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")


class UserUpdate(schemas.BaseUserUpdate):
    """Body for user profile updates."""

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")


class UserRoleUpdate(BaseModel):
    """Request body for promoting or demoting a user's role (admin-only endpoint)."""

    role: Literal["admin", "user"] = Field(description="Target role: 'admin' grants is_superuser; 'user' revokes it.")


class UserCreditsGrant(BaseModel):
    """Request body for granting repository-analysis credits to a user (admin-only, issue 298)."""

    amount: int = Field(ge=1, le=1000, description="Number of analysis credits to add to the user's balance.")


class UserActivityOut(BaseModel):
    """Per-member operational activity for the admin dashboard (superuser only).

    Aggregates a user's activity across ALL projects/workspaces: learning-plan progress, quiz average
    and completion, code-quality engagement (PRs / Issues created), and last activity. Read-only.
    """

    id: uuid.UUID
    email: str
    display_name: str | None = None
    is_superuser: bool = False
    is_demo: bool = False
    last_active_at: datetime | None = None
    created_at: datetime | None = None
    analysis_credits: int = 0

    # 学習プラン: 完了ステップ / 全ステップ（受講状況）。
    learning_plans_count: int = 0
    learning_steps_total: int = 0
    learning_steps_completed: int = 0

    # 理解度テスト: 割当セッション数 / 完了数 / 完了分の平均スコア（0–1 の割合、未受験なら null）。
    quiz_total: int = 0
    quiz_completed: int = 0
    quiz_avg_score: float | None = None

    # コード品質改善への取り組み: 返済 PR 作成数 / Issue 作成数。
    pr_count: int = 0
    issue_count: int = 0
