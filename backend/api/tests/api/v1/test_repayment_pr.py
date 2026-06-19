"""api repayment-PR trigger (issue 033): admin-only 202 enqueue + 404 / 409 guards."""

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1.github import resolve_installation_id
from app.core import db as app_db
from app.main import app
from app.models.project import Project
from app.services.dependencies import get_task_dispatcher, reset_blob_client, reset_task_dispatcher
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, CodeDebt, Job


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


async def _seed(
    client: AsyncClient, *, status_value: str = "open", related_pr: str | None = None
) -> tuple[str, str, uuid.UUID]:
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
        await session.flush()
        run = AnalysisRun(
            project_id=project.id, commit_sha="c", kind=JobType.CODE_DEBT_DETECTION.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        debt = CodeDebt(
            project_id=project.id,
            run_id=run.id,
            file_path="src/a.py",
            type="complexity",
            severity="high",
            code_debt_score=0.8,
            status=status_value,
            related_pr=related_pr,
        )
        session.add(debt)
        await session.commit()
        return org["slug"], "rosetta", debt.id


@pytest.mark.usefixtures("_stub_installation")
async def test_repayment_pr_enqueues_202(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, debt_id = await _seed(authenticated_client)
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/debts/{debt_id}/repayment-pr"
    )
    assert resp.status_code == 202
    job_id = uuid.UUID(resp.json()["job_id"])
    async with app_db.async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.job_type == JobType.REPAYMENT_PR_GENERATION
        assert job.payload["debt_id"] == str(debt_id)
    assert get_task_dispatcher().tasks[0].pipeline == JobType.REPAYMENT_PR_GENERATION.value


@pytest.mark.usefixtures("_stub_installation")
async def test_repayment_pr_404_for_unknown_debt(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _seed(authenticated_client)
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/debts/{uuid.uuid4()}/repayment-pr"
    )
    assert resp.status_code == 404


@pytest.mark.usefixtures("_stub_installation")
async def test_repayment_pr_409_when_already_in_pr(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, debt_id = await _seed(authenticated_client, status_value="in_pr", related_pr="#7")
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/debts/{debt_id}/repayment-pr"
    )
    assert resp.status_code == 409
