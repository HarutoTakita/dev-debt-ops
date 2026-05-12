"""Access-token JWT strategy that enforces `iat >= user.token_epoch`.

Logout bumps `users.token_epoch` to `now()`. A stale access JWT (still within
its 5-minute lifetime but issued before logout) carries an `iat` below the new
epoch and is rejected by `read_token`, closing the ASVS 3.3.1 post-logout gap.
"""

from typing import Any

from fastapi_users.authentication import JWTStrategy
from fastapi_users.jwt import decode_jwt

from app.models.user import User


class EpochCheckedJWTStrategy(JWTStrategy[User, Any]):
    """`JWTStrategy` that additionally enforces `iat >= user.token_epoch`."""

    async def read_token(self, token: str | None, user_manager) -> User | None:  # type: ignore[override]
        """Validate the JWT, then reject if `iat < user.token_epoch`."""
        user = await super().read_token(token, user_manager)
        if user is None or token is None:
            return None
        try:
            data = decode_jwt(
                token,
                self.decode_key,
                self.token_audience,
                algorithms=[self.algorithm],
            )
        except Exception:
            return None
        if int(data.get("iat", 0)) < int(getattr(user, "token_epoch", 0) or 0):
            return None
        return user
