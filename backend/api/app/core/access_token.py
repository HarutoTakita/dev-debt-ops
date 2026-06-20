"""Access-token JWT strategy that enforces `iat >= user.token_epoch`.

Logout bumps `users.token_epoch` to `now()`. A stale access JWT (still within
its 5-minute lifetime but issued before logout) carries an `iat` below the new
epoch and is rejected by `read_token`, closing the ASVS 3.3.1 post-logout gap.

The library's ``JWTStrategy.write_token`` only emits ``sub`` / ``aud`` / ``exp`` — no
``iat`` — so this strategy overrides ``write_token`` to stamp ``iat`` (and ``iss``).
Without it every token would carry ``iat=0``: harmless until the first logout bumps
``token_epoch``, after which *every* freshly-issued token would be rejected forever
(issue-041).
"""

from datetime import UTC, datetime
from typing import Any

from fastapi_users.authentication import JWTStrategy
from fastapi_users.jwt import decode_jwt, generate_jwt

from app.models.user import User

# App-specific issuer isolates access tokens from the reset/verify/OAuth-state tokens that
# share the same signing secret (issue-041, defense in depth).
ACCESS_TOKEN_ISSUER = "rosetta"


class EpochCheckedJWTStrategy(JWTStrategy[User, Any]):
    """`JWTStrategy` that stamps ``iat``/``iss`` on issue and enforces ``iat >= user.token_epoch``."""

    async def write_token(self, user: User) -> str:  # type: ignore[override]
        """Issue a JWT carrying ``iat`` and ``iss`` (in addition to ``sub``/``aud``/``exp``)."""
        data = {
            "sub": str(user.id),
            "aud": self.token_audience,
            "iss": ACCESS_TOKEN_ISSUER,
            "iat": int(datetime.now(UTC).timestamp()),
        }
        return generate_jwt(data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm)

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
