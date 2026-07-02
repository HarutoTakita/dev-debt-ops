"""issue 300: admin user-management endpoints (list + grant credits).

Regression: `GET /users` eager-loads `User.oauth_accounts` (lazy="joined"), so the query result must
call `.unique()` — otherwise it raises InvalidRequestError (the admin screen surfaced this).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


async def _login_admin(email: str) -> AsyncClient:
    """Register + login a user whose email is in ADMIN_EMAILS → auto-promoted to superuser on login."""
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await client.post("/api/v1/auth/register", json={"email": email, "password": "testpassword123"})
    resp = await client.post("/api/v1/auth/login", data={"username": email, "password": "testpassword123"})
    client.cookies = resp.cookies
    return client


async def test_list_users_and_grant_credits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@example.com")
    monkeypatch.setattr(settings, "ANALYSIS_CREDITS_ENABLED", True)
    client = await _login_admin("boss@example.com")
    try:
        # 管理者に昇格していること。
        me = (await client.get("/api/v1/users/me")).json()
        assert me["is_superuser"] is True
        assert me["analysis_credits"] == 0

        # 一覧取得が 200（joined eager load の .unique() 回帰）。
        listed = await client.get("/api/v1/users")
        assert listed.status_code == 200, listed.text
        rows = listed.json()
        assert any(u["email"] == "boss@example.com" for u in rows)
        assert all("analysis_credits" in u for u in rows)

        # クレジット付与 → 残高が増える。
        granted = await client.post(f"/api/v1/users/{me['id']}/credits", json={"amount": 3})
        assert granted.status_code == 200, granted.text
        assert granted.json()["analysis_credits"] == 3
    finally:
        await client.aclose()


async def test_list_users_forbidden_for_general_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "")  # nobody is admin
    client = await _login_admin("plain@example.com")
    try:
        me = (await client.get("/api/v1/users/me")).json()
        assert me["is_superuser"] is False
        assert (await client.get("/api/v1/users")).status_code == 403
    finally:
        await client.aclose()
