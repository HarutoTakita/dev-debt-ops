"""api Twin-Agent endpoints (issue 036): run (202) + activities/pipeline + profiles + retry."""

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1.github import resolve_installation_id
from app.core import db as app_db
from app.main import app
from app.models.project import Project
from app.services.dependencies import get_task_dispatcher, reset_blob_client, reset_task_dispatcher
from shared.enums import JobType
from shared.models import AgentActivity, AgentPipeline, NarrativeStep


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


async def _project(client: AsyncClient) -> tuple[str, str, uuid.UUID]:
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


async def _seed_activity(project_id: uuid.UUID, *, failed_node: bool = False) -> tuple[uuid.UUID, uuid.UUID]:
    async with app_db.async_session_maker() as session:
        node_status = "failed" if failed_node else "succeeded"
        pipeline = AgentPipeline(
            project_id=project_id,
            kind="code_debt",
            status="analyzing",
            stages=[
                {
                    "key": "detect",
                    "label": "検知",
                    "nodes": [{"id": "n-detect", "label": "スキャン", "status": "succeeded", "retryable": False}],
                },
                {
                    "key": "repay",
                    "label": "返済",
                    "nodes": [{"id": "n-repay", "label": "PR", "status": node_status, "retryable": failed_node}],
                },
            ],
        )
        session.add(pipeline)
        await session.flush()
        activity = AgentActivity(
            project_id=project_id, kind="code_debt", headline="掘り起こした", pipeline_id=pipeline.id
        )
        session.add(activity)
        await session.flush()
        session.add(NarrativeStep(activity_id=activity.id, order=0, status="succeeded", message="走査した"))
        await session.commit()
        return activity.id, pipeline.id


async def test_profiles(authenticated_client: AsyncClient) -> None:
    resp = await authenticated_client.get("/api/v1/agents/profiles")
    assert resp.status_code == 200
    kinds = {p["kind"] for p in resp.json()}
    assert kinds == {"code_debt", "knowledge_debt"}


@pytest.mark.usefixtures("_stub_installation")
async def test_run_enqueues_loop(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _project(authenticated_client)
    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/agents/code_debt/run")
    assert resp.status_code == 202
    assert get_task_dispatcher().tasks[0].pipeline == JobType.CODE_DEBT_LOOP.value


@pytest.mark.usefixtures("_stub_installation")
async def test_run_rejects_bad_kind(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _project(authenticated_client)
    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/agents/nope/run")
    assert resp.status_code == 422


async def test_activities_and_pipeline(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _project(authenticated_client)
    activity_id, pipeline_id = await _seed_activity(project_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/agents"

    acts = (await authenticated_client.get(f"{base}/activities?kind=code_debt")).json()
    assert len(acts) == 1
    assert acts[0]["pipeline_id"] == str(pipeline_id)
    assert acts[0]["steps"][0]["message"] == "走査した"

    one = await authenticated_client.get(f"{base}/activities/{activity_id}")
    assert one.status_code == 200

    pipe = await authenticated_client.get(f"{base}/pipelines/{pipeline_id}")
    assert pipe.status_code == 200
    assert len(pipe.json()["stages"]) == 2


@pytest.mark.usefixtures("_stub_installation")
async def test_retry_failed_node_and_409(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _project(authenticated_client)
    _, pipeline_id = await _seed_activity(project_id, failed_node=True)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/agents/pipelines/{pipeline_id}/nodes"

    ok = await authenticated_client.post(f"{base}/n-repay/retry")
    assert ok.status_code == 202
    # the already-succeeded detect node is not retryable → 409
    conflict = await authenticated_client.post(f"{base}/n-detect/retry")
    assert conflict.status_code == 409
