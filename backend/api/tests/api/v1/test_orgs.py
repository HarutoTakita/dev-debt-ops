from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.conftest import register_and_login


async def test_create_org(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        "/api/v1/orgs",
        json={"name": "My Team", "slug": "my-team"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Team"
    assert data["slug"] == "my-team"
    assert data["is_personal"] is False


async def test_list_orgs_includes_personal(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get("/api/v1/orgs")
    assert response.status_code == 200
    orgs = response.json()
    assert len(orgs) == 1
    assert orgs[0]["is_personal"] is True


async def test_org_slug_conflict(authenticated_client: AsyncClient) -> None:
    await authenticated_client.post("/api/v1/orgs", json={"name": "A", "slug": "taken"})
    response = await authenticated_client.post("/api/v1/orgs", json={"name": "B", "slug": "taken"})
    assert response.status_code == 409


async def test_invite_member() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner_client:
        await register_and_login(owner_client, "owner@example.com")
        await owner_client.post("/api/v1/orgs", json={"name": "Team", "slug": "team"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member_client:
        await register_and_login(member_client, "member@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner_client:
        await register_and_login(owner_client, "owner@example.com")
        response = await owner_client.post(
            "/api/v1/orgs/team/members",
            json={"email": "member@example.com"},
        )
        assert response.status_code == 201
        assert response.json()["role"] == "member"


async def test_cannot_invite_to_personal_org(authenticated_client: AsyncClient) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other_client:
        await register_and_login(other_client, "other@example.com")

    orgs = (await authenticated_client.get("/api/v1/orgs")).json()
    personal_slug = orgs[0]["slug"]

    response = await authenticated_client.post(
        f"/api/v1/orgs/{personal_slug}/members",
        json={"email": "other@example.com"},
    )
    assert response.status_code == 403


async def test_member_cannot_invite(authenticated_client: AsyncClient) -> None:
    await authenticated_client.post("/api/v1/orgs", json={"name": "Team", "slug": "team"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member_client:
        await register_and_login(member_client, "member@example.com")

    await authenticated_client.post(
        "/api/v1/orgs/team/members",
        json={"email": "member@example.com"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as third_client:
        await register_and_login(third_client, "third@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member_client:
        await register_and_login(member_client, "member@example.com")
        response = await member_client.post(
            "/api/v1/orgs/team/members",
            json={"email": "third@example.com"},
        )
        assert response.status_code == 403


async def test_nonmember_cannot_access_org(authenticated_client: AsyncClient) -> None:
    await authenticated_client.post("/api/v1/orgs", json={"name": "Private", "slug": "private"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other_client:
        await register_and_login(other_client, "outsider@example.com")
        response = await other_client.get("/api/v1/orgs/private")
        assert response.status_code == 403


async def test_delete_org(authenticated_client: AsyncClient) -> None:
    await authenticated_client.post("/api/v1/orgs", json={"name": "Temp", "slug": "temp"})
    response = await authenticated_client.delete("/api/v1/orgs/temp")
    assert response.status_code == 204

    response = await authenticated_client.get("/api/v1/orgs/temp")
    assert response.status_code == 404


async def test_cannot_delete_personal_org(authenticated_client: AsyncClient) -> None:
    orgs = (await authenticated_client.get("/api/v1/orgs")).json()
    personal_slug = orgs[0]["slug"]
    response = await authenticated_client.delete(f"/api/v1/orgs/{personal_slug}")
    assert response.status_code == 403
