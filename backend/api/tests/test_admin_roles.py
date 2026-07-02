"""issue 300: admin role is .env-driven (ADMIN_EMAILS), reconciled on every login."""

import uuid

import pytest
from fastapi_users.db import SQLAlchemyUserDatabase

from app.core import db as app_db
from app.core.config import settings
from app.core.security import UserManager
from app.models.oauth_account import OAuthAccount
from app.models.user import User


def test_admin_email_set_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", " Boss@Example.com , second@x.io ,")
    assert settings.admin_email_set() == {"boss@example.com", "second@x.io"}
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "")
    assert settings.admin_email_set() == frozenset()


async def _make_user(*, email: str, is_superuser: bool) -> uuid.UUID:
    async with app_db.async_session_maker() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_superuser=is_superuser, is_verified=True)
        session.add(user)
        await session.commit()
        return user.id


async def _login(user_id: uuid.UUID) -> None:
    async with app_db.async_session_maker() as session:
        user = await session.get(User, user_id)
        mgr = UserManager(SQLAlchemyUserDatabase(session, User, OAuthAccount))
        await mgr.on_after_login(user)


async def _is_superuser(user_id: uuid.UUID) -> bool:
    async with app_db.async_session_maker() as session:
        return (await session.get(User, user_id)).is_superuser


async def test_login_promotes_listed_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """A GitHub-SSO user (default general) whose email is listed becomes admin on login."""
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "admin@example.com")
    uid = await _make_user(email="admin@example.com", is_superuser=False)
    await _login(uid)
    assert await _is_superuser(uid) is True


async def test_login_demotes_unlisted_superuser(monkeypatch: pytest.MonkeyPatch) -> None:
    """An account no longer listed is demoted to general on its next login (env is the source of truth)."""
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "someone-else@example.com")
    uid = await _make_user(email="stale-admin@example.com", is_superuser=True)
    await _login(uid)
    assert await _is_superuser(uid) is False


async def test_login_keeps_general_when_no_admins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "")
    uid = await _make_user(email="dev@example.com", is_superuser=False)
    await _login(uid)
    assert await _is_superuser(uid) is False
