from httpx import AsyncClient

from app.core.security import access_cookie_transport, refresh_cookie_transport


async def _register_and_login(client: AsyncClient) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "u@example.com", "password": "testpassword123"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "u@example.com", "password": "testpassword123"},
    )
    assert resp.status_code == 204
    client.cookies = resp.cookies
    return client.cookies[refresh_cookie_transport.cookie_name]


async def test_refresh_without_cookie_returns_401(client: AsyncClient) -> None:
    """/refresh without any cookie must 401 with the uniform detail string."""
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "authentication_required"}


async def test_refresh_rotates_and_issues_new_cookies(client: AsyncClient) -> None:
    """A valid refresh POST rotates the refresh token and re-issues the access cookie."""
    old_refresh = await _register_and_login(client)
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 204
    assert access_cookie_transport.cookie_name in resp.cookies
    new_refresh = resp.cookies[refresh_cookie_transport.cookie_name]
    assert new_refresh != old_refresh


async def test_refresh_detects_reuse_and_revokes_family(client: AsyncClient) -> None:
    """Replaying a rotated-out refresh token 401s and revokes the entire family."""
    stolen = await _register_and_login(client)

    # Legitimate rotation: t1 → t2 (client.cookies now holds t2)
    legit_one = await client.post("/api/v1/auth/refresh")
    assert legit_one.status_code == 204
    t2 = client.cookies[refresh_cookie_transport.cookie_name]
    assert t2 != stolen

    # Attacker replays the pre-rotation token: reuse → revoke the family.
    # Clear the cookie jar first so we don't keep sending the current t2 alongside stolen.
    client.cookies.clear()
    client.cookies.set(refresh_cookie_transport.cookie_name, stolen, domain="test", path="/api/v1/auth/refresh")
    replay = await client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401

    # The legitimate user's t2 is now dead too (whole family revoked).
    client.cookies.clear()
    client.cookies.set(refresh_cookie_transport.cookie_name, t2, domain="test", path="/api/v1/auth/refresh")
    follow_up = await client.post("/api/v1/auth/refresh")
    assert follow_up.status_code == 401
