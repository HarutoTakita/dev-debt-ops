import re
import secrets
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import cast

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_token import EpochCheckedJWTStrategy
from app.core.config import settings
from app.core.db import get_sa_async_session
from app.core.refresh_strategy import RefreshDatabaseStrategy
from app.core.refresh_token_db import RefreshTokenDatabase
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.github_oauth_client import RobustGitHubOAuth2


def _cookie_name(base: str, prefix: str) -> str:
    """Return `{prefix}-{base}` when cookies are Secure (prod), else `base`.

    Browsers reject `__Host-` / `__Secure-` prefixed cookies without the `Secure`
    flag, which breaks local HTTP dev. Switch naming by `COOKIE_SECURE`.
    """
    return f"{prefix}-{base}" if settings.COOKIE_SECURE else base


# --- Access backend (stateless JWT) ------------------------------------------
access_cookie_transport = CookieTransport(
    cookie_name=_cookie_name("access_token", "__Host"),
    cookie_httponly=True,
    cookie_secure=settings.COOKIE_SECURE,
    cookie_samesite="lax",
    cookie_max_age=settings.JWT_LIFETIME_SECONDS,
)


def get_access_jwt_strategy() -> EpochCheckedJWTStrategy:
    """Return an access-token JWT strategy that enforces `iat >= user.token_epoch`.

    Uses an app-specific ``audience`` so access tokens can't be confused with the
    reset/verify/OAuth-state tokens signed by the same secret (issue-041).
    """
    return EpochCheckedJWTStrategy(
        secret=settings.SECRET_KEY.get_secret_value(),
        lifetime_seconds=settings.JWT_LIFETIME_SECONDS,
        token_audience=["rosetta:access"],
    )


access_backend = AuthenticationBackend(
    name="access",
    transport=access_cookie_transport,
    get_strategy=get_access_jwt_strategy,
)


# --- Refresh backend (DB-backed opaque token) --------------------------------
refresh_cookie_transport = CookieTransport(
    cookie_name=_cookie_name("refresh_token", "__Secure"),
    cookie_httponly=True,
    cookie_secure=settings.COOKIE_SECURE,
    cookie_samesite="strict",
    cookie_path="/api/v1/auth/refresh",
    cookie_max_age=settings.REFRESH_TOKEN_LIFETIME_SECONDS,
)


async def get_refresh_token_db(
    session: AsyncSession = Depends(get_sa_async_session),
) -> AsyncGenerator[RefreshTokenDatabase]:
    """Yield a `RefreshTokenDatabase` adapter bound to the request's SA session."""
    yield RefreshTokenDatabase(session, RefreshToken)


def get_refresh_db_strategy(
    db: RefreshTokenDatabase = Depends(get_refresh_token_db),
) -> RefreshDatabaseStrategy:
    """Return a refresh-token strategy that stamps `family_id` + `expires_at` on issue."""
    return RefreshDatabaseStrategy(db, lifetime_seconds=settings.REFRESH_TOKEN_LIFETIME_SECONDS)


refresh_backend = AuthenticationBackend(
    name="refresh",
    transport=refresh_cookie_transport,
    get_strategy=get_refresh_db_strategy,
)


github_oauth_client = RobustGitHubOAuth2(
    settings.GITHUB_CLIENT_ID,
    settings.GITHUB_CLIENT_SECRET.get_secret_value(),
)


async def get_user_db(session: AsyncSession = Depends(get_sa_async_session)):
    """Yield a fastapi-users SQLAlchemy database adapter as a FastAPI dependency.

    Yields:
        A `SQLAlchemyUserDatabase` instance bound to the current session.
    """
    from app.models.oauth_account import OAuthAccount

    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """fastapi-users lifecycle manager with custom post-registration and post-login hooks.

    `on_after_register` creates a personal org for every new user. The org slug is derived
    from the email prefix (lowercased, non-alphanumeric characters replaced with hyphens).
    If the slug is already taken, up to 10 retries are attempted with a random hex suffix,
    relying on the `uq_orgs_slug_active` partial unique index to avoid TOCTOU races.

    `on_after_login` stamps `last_active_at` on the `User` row on every successful login.
    """

    reset_password_token_secret = settings.SECRET_KEY.get_secret_value()
    verification_token_secret = settings.SECRET_KEY.get_secret_value()

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        """Create a personal org for every new user.

        Raises:
            RuntimeError: If a unique slug cannot be generated after 10 retries.
        """
        from app.models.org import Org, OrgMember, OrgRole

        # `.session` is defined on SQLAlchemyUserDatabase but not the BaseUserDatabase protocol.
        session = cast(SQLAlchemyUserDatabase[User, uuid.UUID], self.user_db).session

        # Derive slug from email prefix
        base_slug = re.sub(r"[^a-z0-9-]", "-", user.email.split("@")[0].lower()).strip("-")
        if len(base_slug) < 3:
            base_slug = base_slug + "-user"

        # Attempt insert, retry with random suffix on slug collision
        # (relies on uq_orgs_slug_active partial unique index — no TOCTOU race)
        slug = base_slug
        display_name = user.display_name or user.email.split("@")[0]

        for _attempt in range(10):
            try:
                org = Org(name=display_name, slug=slug, is_personal=True, created_by=user.id)
                session.add(org)
                await session.flush()
                break
            except IntegrityError:
                await session.rollback()
                slug = f"{base_slug}-{secrets.token_hex(3)}"
        else:
            raise RuntimeError(f"Could not generate unique slug for base: {base_slug}")

        member = OrgMember(user_id=user.id, org_id=org.id, role=OrgRole.OWNER)
        session.add(member)
        await session.commit()

    async def on_after_login(
        self,
        user: User,
        request: Request | None = None,
        response: object | None = None,
    ) -> None:
        """Stamp `last_active_at` and reconcile the admin role from `ADMIN_EMAILS` (issue 300).

        Roles are `.env`-driven: `is_superuser` is set to whether the user's email is listed in
        `ADMIN_EMAILS`, so GitHub-SSO users are general users unless explicitly named (and any account
        no longer listed is demoted on its next login). This is the single source of truth for admin.
        """
        session = cast(SQLAlchemyUserDatabase[User, uuid.UUID], self.user_db).session
        user.last_active_at = datetime.now(UTC)
        desired_admin = user.email.lower() in settings.admin_email_set()
        if user.is_superuser != desired_admin:
            user.is_superuser = desired_admin
        session.add(user)
        await session.commit()


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db),
) -> AsyncGenerator[UserManager]:
    """Yield a `UserManager` instance as a FastAPI dependency.

    Yields:
        A `UserManager` bound to the injected user database adapter.
    """
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [access_backend, refresh_backend],
)

current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
