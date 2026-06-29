"""api agentic-analysis trigger: ``POST .../agentic-analysis`` enqueues (202) without running.

The Twin Agent runs in the ``service`` container (issue 069); api only enqueues. Mirrors the
``detect-debts`` test: ``resolve_installation_id`` is stubbed (no GitHub), singletons reset.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1.github import resolve_installation_id
from app.core import db as app_db
from app.main import app
from app.models.project import Project
from app.services.dependencies import get_task_dispatcher, reset_blob_client, reset_task_dispatcher
from shared.enums import JobStatus, JobType
from shared.models import Job


@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_task_dispatcher()
    reset_blob_client()
    yield
    reset_task_dispatcher()
    reset_blob_client()


@pytest.fixture
def _stub_installation():
    app.dependency_overrides[resolve_installation_id] = lambda: 12345678
    yield 12345678
    app.dependency_overrides.pop(resolve_installation_id, None)


async def _seed_project(client: AsyncClient) -> tuple[str, str]:
    """Create a project in the caller's first org; return (org_slug, project_slug)."""
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
    return org["slug"], "rosetta"


@pytest.mark.usefixtures("_stub_installation")
async def test_agentic_analysis_enqueues_and_returns_202(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug = await _seed_project(authenticated_client)

    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/agentic-analysis")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "QUEUED"
    job_id = uuid.UUID(body["job_id"])

    async with app_db.async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.job_type == JobType.AGENTIC_ANALYSIS
        assert job.status == JobStatus.QUEUED
        assert job.payload["owner"] == "acme"
        assert job.payload["github"] == {"installation_id": 12345678}
        assert "access_token" not in job.payload["github"]
        assert "project_id" in job.payload

    dispatcher = get_task_dispatcher()
    assert len(dispatcher.tasks) == 1
    assert dispatcher.tasks[0].pipeline == JobType.AGENTIC_ANALYSIS.value
    assert dispatcher.tasks[0].dedup_key == str(job_id)
