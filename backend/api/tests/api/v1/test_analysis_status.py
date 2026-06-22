"""api analysis-status (cockpit rehydration): latest job status per analysis JobType."""

import uuid

from httpx import AsyncClient

from app.core import db as app_db
from app.models.project import Project
from shared.enums import JobStatus, JobType
from shared.models import Job


async def _seed_project(client: AsyncClient) -> tuple[str, str, uuid.UUID, uuid.UUID]:
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
        return org["slug"], "rosetta", project.id, user_id


async def test_analysis_status_empty(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/analysis-status")
    assert resp.status_code == 200
    assert resp.json() == {"jobs": {}}


async def test_analysis_status_returns_latest_per_type(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, user_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        # An older FAILED then a newer COMPLETED code-debt job → latest (COMPLETED) wins.
        session.add(
            Job(
                job_type=JobType.CODE_DEBT_DETECTION,
                status=JobStatus.FAILED,
                payload={},
                project_id=project_id,
                created_by=user_id,
            )
        )
        await session.commit()
        latest_code = Job(
            job_type=JobType.CODE_DEBT_DETECTION,
            status=JobStatus.COMPLETED,
            payload={},
            project_id=project_id,
            created_by=user_id,
        )
        kc = Job(
            job_type=JobType.KC_ANALYSIS,
            status=JobStatus.PROCESSING,
            payload={},
            project_id=project_id,
            created_by=user_id,
        )
        # A job for a different project must not leak in.
        other = Job(
            job_type=JobType.KNOWLEDGE_DEBT_DETECTION,
            status=JobStatus.COMPLETED,
            payload={},
            project_id=uuid.uuid4(),
            created_by=user_id,
        )
        session.add_all([latest_code, kc, other])
        await session.commit()
        latest_code_id = str(latest_code.id)

    body = (await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/analysis-status")).json()
    jobs = body["jobs"]
    assert jobs["code_debt_detection"]["status"] == "COMPLETED"
    assert jobs["code_debt_detection"]["job_id"] == latest_code_id  # newest of the two
    assert jobs["kc_analysis"]["status"] == "PROCESSING"
    assert "knowledge_debt_detection" not in jobs  # other project's job excluded
