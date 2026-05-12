"""`DatabaseStrategy` subclass that stamps rotation metadata on write.

`fastapi_users.authentication.strategy.db.DatabaseStrategy._create_access_token_dict`
returns only `token` and `user_id`. The `RefreshToken` model requires
`family_id` and `expires_at`, so the subclass fills them in at write time.

On initial issue (login), `family_id = token` — the new row anchors the
chain. On rotation (inside `/auth/refresh`), the route handler creates the
new row directly via the `RefreshTokenDatabase` adapter so it can preserve
the existing `family_id`; this strategy's `write_token` is therefore only
used for the initial issue.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi_users.authentication.strategy.db import DatabaseStrategy

from app.core.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User


class RefreshDatabaseStrategy(DatabaseStrategy):  # type: ignore[type-arg]
    """`DatabaseStrategy` that stamps `family_id` and `expires_at` on write."""

    def _create_access_token_dict(self, user: User) -> dict[str, Any]:  # type: ignore[override]
        token = secrets.token_urlsafe(32)
        return {
            "token": token,
            "user_id": user.id,
            "family_id": token,
            "expires_at": datetime.now(UTC) + timedelta(seconds=settings.REFRESH_TOKEN_LIFETIME_SECONDS),
        }


__all__ = ["RefreshDatabaseStrategy", "RefreshToken"]
