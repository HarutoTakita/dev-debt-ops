"""api baseline quizzes (issue 054): ``POST .../baseline-quizzes`` creates per-feature sessions.

Installation-id is stubbed; the mock dispatcher / blob are reset. Asserts one session + one
generation Job per feature, idempotent skip, and 409 when clustering has not run.
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
from shared.models import AnalysisRun, Feature, FeatureFile, QuizSession


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


async def _seed_features(project_id: uuid.UUID, keys: list[str]) -> None:
    async with app_db.async_session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.FEATURE_CLUSTERING.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        for k in keys:
            feat = Feature(project_id=project_id, run_id=run.id, key=k, name=k.title())
            session.add(feat)
            await session.flush()
            session.add(FeatureFile(run_id=run.id, feature_id=feat.id, file_path=f"src/{k}.py", confidence=0.9))
        await session.commit()


@pytest.mark.usefixtures("_stub_installation")
async def test_baseline_409_without_clustering(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/baseline-quizzes")
    assert resp.status_code == 409


@pytest.mark.usefixtures("_stub_installation")
async def test_baseline_creates_session_and_job_per_feature(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed_features(project_id, ["auth", "billing"])

    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/baseline-quizzes")
    assert resp.status_code == 202
    body = resp.json()
    assert body["created"] == 2
    assert len(body["job_ids"]) == 2

    async with app_db.async_session_maker() as session:
        from sqlalchemy import func, select

        n = (
            await session.execute(
                select(func.count()).select_from(QuizSession).where(QuizSession.project_id == project_id)
            )
        ).scalar_one()
        assert n == 2
        sessions = (await session.execute(select(QuizSession).where(QuizSession.project_id == project_id))).scalars()
        for qs in sessions:
            assert qs.granularity == "feature"
            assert qs.is_baseline is True
            assert qs.feature_id is not None

    dispatcher = get_task_dispatcher()
    assert len(dispatcher.tasks) == 2
    assert all(t.pipeline == JobType.QUIZ_GENERATION.value for t in dispatcher.tasks)


@pytest.mark.usefixtures("_stub_installation")
async def test_baseline_is_idempotent(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed_features(project_id, ["auth"])

    first = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/baseline-quizzes")
    assert first.json()["created"] == 1
    reset_task_dispatcher()
    second = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/baseline-quizzes")
    assert second.json()["created"] == 0  # open baseline session already exists → skipped
