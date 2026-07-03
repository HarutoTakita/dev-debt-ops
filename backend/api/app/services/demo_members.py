"""Fabricated workspace members for the guest-demo admin dashboard (richer-demo issue).

The guest-demo user is **not** a superuser and must never see real users' data. When a demo guest opens
the admin dashboard (``GET /users/activity``), we serve this hand-crafted set of sample members so the
"business operations" management view looks populated and realistic — without leaking any real account.
Read-only: the demo cannot grant credits or change roles (those endpoints stay superuser-only).
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.schemas.user import UserActivityOut

# Stable namespace for the fabricated members' ids (isolated from other seeders).
_NS = uuid.UUID("0de0b6b3-7c1e-4f8a-9d2e-069000000300")

# (display_name, email, active-minutes-ago, plans, steps_total, steps_done,
#  quiz_total, quiz_done, avg_score|None, pr, issue, credits, is_admin)
_MEMBERS: list[tuple[str, str, int, int, int, int, int, int, float | None, int, int, int, bool]] = [
    ("高橋 恵", "takahashi@sample-shop.demo", 12, 3, 10, 10, 14, 14, 0.91, 8, 4, 40, True),
    ("山本 大和", "yamamoto@sample-shop.demo", 5 * 60, 2, 11, 7, 14, 11, 0.79, 3, 2, 15, False),
    ("田中 拓也", "tanaka@sample-shop.demo", 90, 2, 10, 8, 14, 12, 0.82, 5, 3, 20, False),
    ("佐藤 みな", "sato@sample-shop.demo", 26 * 60, 2, 12, 6, 14, 9, 0.74, 2, 1, 8, False),
    ("鈴木 一郎", "suzuki@sample-shop.demo", 3 * 24 * 60, 1, 9, 3, 14, 5, 0.61, 1, 0, 3, False),
    ("渡辺 さくら", "watanabe@sample-shop.demo", 12 * 24 * 60, 1, 8, 1, 14, 0, None, 0, 0, 0, False),
]


def demo_member_activity() -> list[UserActivityOut]:
    """Return the fabricated demo workspace members with plausible, varied activity metrics.

    Timestamps are computed relative to now so "last active" always reads as recent/varied. Ids are
    deterministic (uuid5) so re-renders are stable.
    """
    now = datetime.now(UTC)
    members: list[UserActivityOut] = []
    for (
        name,
        email,
        mins,
        plans,
        steps_total,
        steps_done,
        q_total,
        q_done,
        avg,
        pr,
        issue,
        credits,
        is_admin,
    ) in _MEMBERS:
        members.append(
            UserActivityOut(
                id=uuid.uuid5(_NS, email),
                email=email,
                display_name=name,
                is_superuser=is_admin,
                is_demo=False,
                last_active_at=now - timedelta(minutes=mins),
                created_at=now - timedelta(days=90),
                analysis_credits=credits,
                learning_plans_count=plans,
                learning_steps_total=steps_total,
                learning_steps_completed=steps_done,
                quiz_total=q_total,
                quiz_completed=q_done,
                quiz_avg_score=avg,
                pr_count=pr,
                issue_count=issue,
            )
        )
    return members
