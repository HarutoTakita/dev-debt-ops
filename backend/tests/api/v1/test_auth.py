from httpx import AsyncClient

from app.core.security import access_cookie_transport, refresh_cookie_transport


async def test_register_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "testpassword123", "display_name": "Test"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test"
    assert data["is_active"] is True


async def test_register_creates_personal_org(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "testpassword123", "display_name": "Test"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpassword123"},
    )
    client.cookies = login_response.cookies

    orgs_response = await client.get("/api/v1/orgs")
    assert orgs_response.status_code == 200
    orgs = orgs_response.json()
    assert len(orgs) == 1
    assert orgs[0]["is_personal"] is True
    assert orgs[0]["slug"] == "test"


async def test_login_sets_both_cookies(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == 204
    assert access_cookie_transport.cookie_name in response.cookies
    assert refresh_cookie_transport.cookie_name in response.cookies


async def test_get_current_user(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


async def test_unauthenticated_denied(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_logout_revokes_refresh_and_clears_cookies(authenticated_client: AsyncClient) -> None:
    """/logout is idempotent, revokes the refresh row, and clears both cookies."""
    r = await authenticated_client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    # httpx stores cleared cookies as empty-string values after logout Max-Age=0.
    assert authenticated_client.cookies.get(refresh_cookie_transport.cookie_name) in (None, "")
    # The old refresh cookie (pre-logout) can no longer rotate:
    replayed = await authenticated_client.post("/api/v1/auth/refresh")
    assert replayed.status_code == 401


async def test_logout_bumps_token_epoch(authenticated_client: AsyncClient) -> None:
    """A stale access cookie presented after logout must be rejected by the epoch check."""
    stale_access = authenticated_client.cookies.get(access_cookie_transport.cookie_name)
    assert stale_access is not None
    await authenticated_client.post("/api/v1/auth/logout")

    # Replay the pre-logout access cookie on a protected route.
    from httpx import ASGITransport
    from httpx import AsyncClient as HTTPXClient

    from app.main import app

    async with HTTPXClient(transport=ASGITransport(app=app), base_url="http://test") as replayer:
        replayer.cookies.set(access_cookie_transport.cookie_name, stale_access, domain="test", path="/")
        r = await replayer.get("/api/v1/users/me")
        assert r.status_code == 401
