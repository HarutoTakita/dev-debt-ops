"""api code-graph delivery (issue 235): unobserved empty 200 + persisted snapshot projection."""

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient

from app.core import db as app_db
from app.models.project import Project
from shared.models import CodeGraph


async def _seed_project(client: AsyncClient) -> tuple[str, str, uuid.UUID]:
    me = (await client.get("/api/v1/users/me")).json()
    user_id = uuid.UUID(me["id"])
    org = (await client.get("/api/v1/orgs")).json()[0]
    async with app_db.async_session_maker() as session:
        project = Project(
            org_id=uuid.UUID(org["id"]),
            name="Rosetta",
            slug="rosetta",
            repo_owner="acme",
            repo_name="rosetta",
            repo_full_name="acme/rosetta",
            default_branch="main",
            created_by=user_id,
        )
        session.add(project)
        await session.commit()
        return org["slug"], "rosetta", project.id


async def test_code_graph_unobserved_returns_empty(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is False
    assert body["file_edges"] == []


async def test_code_graph_returns_persisted_snapshot(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        session.add(
            CodeGraph(
                project_id=project_id,
                computed_at=datetime.now(UTC),
                graph={"file_edges": [{"source": "pkg/main.py", "target": "pkg/util.py"}]},
            )
        )
        await session.commit()
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is True
    assert body["file_edges"] == [{"source": "pkg/main.py", "target": "pkg/util.py"}]
