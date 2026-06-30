"""Tests for the guest-demo auth flow (issue 069).

``DEMO_MODE_ENABLED`` is false in tests, so ``auth.py`` does not mount the demo router.
We mount it here directly — the endpoint logic itself is flag-independent — and exercise
login, idempotency (single shared user), and the ``is_demo`` GitHub/write guard.
"""

from httpx import AsyncClient

from app.api.v1.auth_demo import router as _demo_router
from app.main import app

# Mount once (guard against re-import double-registration).
if not any(getattr(r, "path", None) == "/api/v1/auth/demo" for r in app.routes):
    app.include_router(_demo_router, prefix="/api/v1/auth")


async def test_config_endpoint_exposes_demo_flag(client: AsyncClient) -> None:
    """GET /api/v1/config returns the public ``demo_mode_enabled`` flag (a bool)."""
    resp = await client.get("/api/v1/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "demo_mode_enabled" in body
    assert isinstance(body["demo_mode_enabled"], bool)


async def test_demo_login_sets_session_and_is_demo(client: AsyncClient) -> None:
    """POST /api/v1/auth/demo sets auth cookies; /users/me then reports the demo user."""
    resp = await client.post("/api/v1/auth/demo")
    assert resp.status_code == 204
    assert "set-cookie" in {k.lower() for k in resp.headers}

    client.cookies = resp.cookies
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    body = me.json()
    assert body["is_demo"] is True
    assert body["email"] == "demo@devdebtops.example"
    assert body["is_superuser"] is False


async def test_demo_login_is_idempotent_shared_user(client: AsyncClient) -> None:
    """Repeated demo logins resolve to the same shared demo user (no duplicate accounts)."""
    first = await client.post("/api/v1/auth/demo")
    client.cookies = first.cookies
    id1 = (await client.get("/api/v1/users/me")).json()["id"]

    client.cookies.clear()
    second = await client.post("/api/v1/auth/demo")
    client.cookies = second.cookies
    id2 = (await client.get("/api/v1/users/me")).json()["id"]

    assert id1 == id2


async def test_demo_user_can_browse_seeded_repos(client: AsyncClient) -> None:
    """A demo user CAN browse repositories — they get seeded sample repos (200), not a 403.

    Read-only repo-browse routes (repositories / branches / tree / contents) were opened to the
    guest demo (issue 069: "repo ブラウズ対応に拡張") so the new-project repo picker and the file
    browser are demoable. Write/analysis routes stay blocked for demo users via the strict
    GitHub-client dependency (``resolve_installation_id`` raises 403 ``demo_readonly``).
    """
    resp = await client.post("/api/v1/auth/demo")
    client.cookies = resp.cookies

    gh = await client.get("/api/v1/github/repositories")
    assert gh.status_code == 200
    repos = gh.json()["repositories"]
    assert isinstance(repos, list)
    assert len(repos) > 0  # seeded sample repos, not a real GitHub call
