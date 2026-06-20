"""api learning-plan endpoints (issue 035): generate (202) + get + step PATCH."""

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1.github import resolve_installation_id
from app.core import db as app_db
from app.main import app
from app.models.project import Project
from app.services.dependencies import get_task_dispatcher, reset_blob_client, reset_task_dispatcher
from shared.enums import JobType
from shared.models import LearningPlan, LearningResource, LearningStep, QuizResult, QuizSession


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


async def _seed_plan(project_id: uuid.UUID) -> uuid.UUID:
    async with app_db.async_session_maker() as session:
        team = LearningResource(
            project_id=project_id,
            origin="team",
            kind="adr",
            title="ADR-0001",
            source_ref="docs/adr/0001.md",
            priority="required",
            estimated_minutes=15,
            dormant_days=120,
        )
        ext = LearningResource(
            project_id=project_id,
            origin="external",
            kind="docs",
            title="Docs",
            url="https://x/y",
            priority="recommended",
            estimated_minutes=30,
        )
        plan = LearningPlan(project_id=project_id, gap_concepts=["cache"], estimated_total_minutes=45)
        session.add_all([team, ext, plan])
        await session.flush()
        session.add_all(
            [
                LearningStep(plan_id=plan.id, order=0, completed=False, resource_id=team.id),
                LearningStep(plan_id=plan.id, order=1, completed=False, resource_id=ext.id),
            ]
        )
        await session.commit()
        return plan.id


@pytest.mark.usefixtures("_stub_installation")
async def test_generate_returns_202_and_plan_id(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _project(authenticated_client)
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans", json={"gap_concepts": ["cache"]}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "plan_id" in body
    assert get_task_dispatcher().tasks[0].pipeline == JobType.LEARNING_PLAN_GENERATION.value
    # The plan row exists immediately (so the frontend can poll then GET it).
    async with app_db.async_session_maker() as session:
        assert await session.get(LearningPlan, uuid.UUID(body["plan_id"])) is not None


async def test_get_plan_team_first(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _project(authenticated_client)
    plan_id = await _seed_plan(project_id)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans/{plan_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gap_concepts"] == ["cache"]
    assert [s["resource"]["origin"] for s in body["steps"]] == ["team", "external"]
    assert body["steps"][0]["resource"]["dormant_days"] == 120
    assert body["estimated_total_minutes"] == 45


async def test_get_plan_404(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _project(authenticated_client)
    resp = await authenticated_client.get(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans/{uuid.uuid4()}"
    )
    assert resp.status_code == 404


async def test_patch_step_completed(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _project(authenticated_client)
    plan_id = await _seed_plan(project_id)
    resp = await authenticated_client.patch(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans/{plan_id}/steps/0",
        json={"completed": True},
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] is True
    # persisted
    get = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans/{plan_id}")
    steps = {s["order"]: s for s in get.json()["steps"]}
    assert steps[0]["completed"] is True


async def test_get_plan_403_for_other_developers_plan(authenticated_client: AsyncClient) -> None:
    """A plan owned by another developer is not readable (issue-040)."""
    org_slug, project_slug, project_id = await _project(authenticated_client)
    async with app_db.async_session_maker() as session:
        plan = LearningPlan(project_id=project_id, developer_id=uuid.uuid4(), gap_concepts=["x"])
        session.add(plan)
        await session.commit()
        plan_id = plan.id
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans/{plan_id}")
    assert resp.status_code == 403


@pytest.mark.usefixtures("_stub_installation")
async def test_generate_403_for_other_developers_attempt(authenticated_client: AsyncClient) -> None:
    """attempt_id belonging to another developer must not be readable (issue-040 IDOR)."""
    org_slug, project_slug, project_id = await _project(authenticated_client)
    async with app_db.async_session_maker() as session:
        other_session = QuizSession(
            project_id=project_id,
            developer_id=uuid.uuid4(),  # someone else
            file_path="src/a.py",
            repo_full_name="acme/rosetta",
            questions=[],
            answer_key={},
        )
        session.add(other_session)
        await session.flush()
        session.add(
            QuizResult(
                session_id=other_session.id,
                understood=[],
                gap_concepts=[{"id": "secret-gap", "label": "leaked"}],
                kc_before=0.1,
                kc_after=0.2,
            )
        )
        await session.commit()
        attempt_id = other_session.id
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans?attempt_id={attempt_id}"
    )
    assert resp.status_code == 403
