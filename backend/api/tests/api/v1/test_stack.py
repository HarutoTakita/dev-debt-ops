"""api stack-analysis: enqueue (202), job polling result shape, and stale-job cleanup.

The heavy agent runs in the ``service`` container (issue 018); api only enqueues and reads.
``resolve_installation_id`` is overridden so the test never touches GitHub, and the
process-singleton mock dispatcher / blob are reset between tests.
"""

import importlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.api.deps import get_github_app_service
from app.api.v1.github import resolve_installation_id
from app.core import db as app_db
from app.main import app
from app.services.dependencies import reset_blob_client, reset_task_dispatcher
from app.services.job_orchestrator import timeout_stale_jobs
from shared.enums import JobStatus, JobType
from shared.models import Job, TechStack

_CATS = ("frameworks", "databases", "auth", "container", "infra", "cicd", "monitoring", "testing", "other")

_INSTALLATION_ID = 12345678


class _StubGitHubApp:
    """Stub GitHubAppService whose repo→installation mapping is set per test (issue-039)."""

    def __init__(self, repo_installation: int) -> None:
        self._repo_installation = repo_installation

    async def get_installation_for_repo(self, owner: str, repo: str) -> int:
        return self._repo_installation


@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_task_dispatcher()
    reset_blob_client()
    yield
    reset_task_dispatcher()
    reset_blob_client()


@pytest.fixture
def _stub_installation():
    """Override installation resolution + the GitHub App so no external call is made.

    By default the repo's managing installation matches the caller's, so ``verify_repo_access``
    passes. Tests that need a mismatch override ``get_github_app_service`` themselves.
    """
    app.dependency_overrides[resolve_installation_id] = lambda: _INSTALLATION_ID
    app.dependency_overrides[get_github_app_service] = lambda: _StubGitHubApp(_INSTALLATION_ID)
    yield _INSTALLATION_ID
    app.dependency_overrides.pop(resolve_installation_id, None)
    app.dependency_overrides.pop(get_github_app_service, None)


@pytest.mark.usefixtures("_stub_installation")
async def test_analyze_stack_enqueues_and_returns_202(authenticated_client: AsyncClient) -> None:
    from app.services.dependencies import get_task_dispatcher

    resp = await authenticated_client.post("/api/v1/github/repositories/acme/rosetta/analyze-stack")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "QUEUED"
    job_id = uuid.UUID(body["job_id"])

    # The Job row exists as QUEUED with the method-B payload (installation_id only, no secret).
    async with app_db.async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.job_type == JobType.STACK_ANALYSIS
        assert job.status == JobStatus.QUEUED
        assert job.payload["owner"] == "acme"
        assert job.payload["github"] == {"installation_id": 12345678}
        assert "access_token" not in job.payload["github"]

    # The dispatcher was called exactly once for the stack_analysis pipeline.
    dispatcher = get_task_dispatcher()
    assert len(dispatcher.tasks) == 1
    assert dispatcher.tasks[0].pipeline == JobType.STACK_ANALYSIS.value
    assert dispatcher.tasks[0].dedup_key == str(job_id)


async def test_get_stack_requires_authentication(client: AsyncClient) -> None:
    """Unauthenticated GET .../stack is rejected (issue-039: was previously open)."""
    resp = await client.get("/api/v1/github/repositories/acme/rosetta/stack")
    assert resp.status_code == 401


@pytest.mark.usefixtures("_stub_installation")
async def test_get_stack_returns_cached_for_accessible_repo(authenticated_client: AsyncClient) -> None:
    """A repo managed by the caller's installation returns its cached analysis."""
    async with app_db.async_session_maker() as session:
        session.add(
            TechStack(
                owner="acme",
                repo="rosetta",
                analyzed_at=datetime.now(UTC),
                languages=[{"name": "Python", "confidence": "high"}],
                categories={k: [] for k in _CATS},
            )
        )
        await session.commit()

    resp = await authenticated_client.get("/api/v1/github/repositories/acme/rosetta/stack")
    assert resp.status_code == 200
    assert resp.json()["owner"] == "acme"


async def test_get_stack_404_when_installation_does_not_manage_repo(authenticated_client: AsyncClient) -> None:
    """Cross-tenant read: the repo is managed by a different installation → 404, no leak."""
    app.dependency_overrides[resolve_installation_id] = lambda: _INSTALLATION_ID
    app.dependency_overrides[get_github_app_service] = lambda: _StubGitHubApp(99999999)  # different installation
    try:
        async with app_db.async_session_maker() as session:
            session.add(
                TechStack(
                    owner="victim",
                    repo="private",
                    analyzed_at=datetime.now(UTC),
                    languages=[{"name": "Go", "confidence": "high"}],
                    categories={k: [] for k in _CATS},
                )
            )
            await session.commit()

        resp = await authenticated_client.get("/api/v1/github/repositories/victim/private/stack")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(resolve_installation_id, None)
        app.dependency_overrides.pop(get_github_app_service, None)


async def test_analyze_stack_404_when_installation_does_not_manage_repo(authenticated_client: AsyncClient) -> None:
    """Triggering analysis for a repo the caller's installation can't manage → 404."""
    app.dependency_overrides[resolve_installation_id] = lambda: _INSTALLATION_ID
    app.dependency_overrides[get_github_app_service] = lambda: _StubGitHubApp(99999999)
    try:
        resp = await authenticated_client.post("/api/v1/github/repositories/victim/private/analyze-stack")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(resolve_installation_id, None)
        app.dependency_overrides.pop(get_github_app_service, None)


async def test_api_does_not_import_the_agent() -> None:
    """The ADK agent moved to the service; api must not ship it (no sync execution)."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.agent.stack_agent")


async def test_get_job_returns_status_trace_and_tech_stack(authenticated_client: AsyncClient) -> None:
    me = (await authenticated_client.get("/api/v1/users/me")).json()
    user_id = uuid.UUID(me["id"])
    trace = ["[call] list_key_files(owner='acme', repo='rosetta')", "[done] list_key_files", "[summary] 完了"]

    async with app_db.async_session_maker() as session:
        job = Job(
            job_type=JobType.STACK_ANALYSIS,
            status=JobStatus.COMPLETED,
            payload={"owner": "acme", "repo": "rosetta", "branch": "main"},
            result_data={"agentTrace": trace, "languages": [], "categories": {}},
            created_by=user_id,
            completed_at=datetime.now(UTC),
        )
        session.add(job)
        session.add(
            TechStack(
                owner="acme",
                repo="rosetta",
                analyzed_at=datetime.now(UTC),
                languages=[{"name": "Python", "confidence": "high"}],
                categories={k: [] for k in _CATS},
            )
        )
        await session.commit()
        job_id = job.id

    resp = await authenticated_client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["agent_trace"] == trace
    assert body["tech_stack"]["owner"] == "acme"
    assert body["tech_stack"]["languages"][0]["name"] == "Python"


async def test_stale_processing_jobs_are_failed() -> None:
    """The api-side cleanup fails PROCESSING jobs whose started_at is older than the cutoff."""
    async with app_db.async_session_maker() as session:
        stale = Job(
            job_type=JobType.STACK_ANALYSIS,
            status=JobStatus.PROCESSING,
            payload={"owner": "acme", "repo": "rosetta"},
            started_at=datetime.now(UTC) - timedelta(hours=2),
        )
        fresh = Job(
            job_type=JobType.STACK_ANALYSIS,
            status=JobStatus.PROCESSING,
            payload={},
            started_at=datetime.now(UTC),
        )
        session.add(stale)
        session.add(fresh)
        await session.commit()
        stale_id, fresh_id = stale.id, fresh.id

    async with app_db.async_session_maker() as session:
        timed_out = await timeout_stale_jobs(session, max_age=timedelta(hours=1))
        assert stale_id in timed_out
        assert fresh_id not in timed_out

    async with app_db.async_session_maker() as session:
        assert (await session.get(Job, stale_id)).status == JobStatus.FAILED
        assert (await session.get(Job, fresh_id)).status == JobStatus.PROCESSING
