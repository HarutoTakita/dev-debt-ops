"""api quiz endpoints (issue 034): generate/list/get/answer/submit/result + authz.

The generation/grading pipelines run in service; api creates the session, enqueues, serves, and
strips the answer key. Installation id is stubbed; the mock dispatcher is reset.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1.github import resolve_installation_id
from app.core import db as app_db
from app.main import app
from app.models.project import Project
from app.services.dependencies import get_task_dispatcher, reset_blob_client, reset_task_dispatcher
from shared.enums import JobType
from shared.models import QuizResult, QuizSession


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


async def _project(client: AsyncClient) -> tuple[str, str, uuid.UUID, uuid.UUID]:
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


async def _seed_session(project_id: uuid.UUID, developer_id: uuid.UUID, **kw) -> uuid.UUID:
    async with app_db.async_session_maker() as session:
        qs = QuizSession(
            project_id=project_id,
            developer_id=developer_id,
            file_path="src/a.py",
            repo_full_name="acme/rosetta",
            questions=[{"id": "q1", "kind": "free_text", "prompt": "?", "difficulty": "L1"}],
            answer_key={"q1": {"answer": "x", "rubric": "y"}},
            **kw,
        )
        session.add(qs)
        await session.commit()
        return qs.id


@pytest.mark.usefixtures("_stub_installation")
async def test_generate_enqueues_and_creates_session(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _, _ = await _project(authenticated_client)
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/generate", json={"file_path": "src/a.py"}
    )
    assert resp.status_code == 202
    assert get_task_dispatcher().tasks[0].pipeline == JobType.QUIZ_GENERATION.value


async def test_get_session_strips_answer_key_and_normalizes(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_session(project_id, user_id)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["file"] == {"path": "src/a.py", "repo_full_name": "acme/rosetta"}
    q = body["questions"][0]
    assert "answer" not in q  # answer key never delivered
    assert q["code_snippet"] is None  # normalized to satisfy the contract


async def test_save_answer_upsert_and_status(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_session(project_id, user_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}/answers"
    r1 = await authenticated_client.patch(base, json={"question_id": "q1", "value": "first"})
    assert r1.status_code == 200
    r2 = await authenticated_client.patch(base, json={"question_id": "q1", "value": "second"})
    assert r2.json()["value"] == "second"  # upsert
    # session moved to in_progress
    async with app_db.async_session_maker() as session:
        qs = await session.get(QuizSession, sid)
        assert qs.status == "in_progress"


@pytest.mark.usefixtures("_stub_installation")
async def test_submit_enqueues_grading(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_session(project_id, user_id)
    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}/submit")
    assert resp.status_code == 202
    assert get_task_dispatcher().tasks[0].pipeline == JobType.QUIZ_GRADING.value
    async with app_db.async_session_maker() as session:
        assert (await session.get(QuizSession, sid)).status == "grading"


async def test_result_404_until_graded(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_session(project_id, user_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}/result"
    assert (await authenticated_client.get(base)).status_code == 404
    async with app_db.async_session_maker() as session:
        session.add(
            QuizResult(
                session_id=sid, understood=[{"id": "c1", "label": "ok"}], gap_concepts=[], kc_before=0.2, kc_after=0.6
            )
        )
        await session.commit()
    res = await authenticated_client.get(base)
    assert res.status_code == 200
    assert res.json()["kc_after"] == 0.6


async def test_other_users_session_is_403(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, _ = await _project(authenticated_client)
    sid = await _seed_session(project_id, uuid.uuid4())  # someone else's session
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}")
    assert resp.status_code == 403


@pytest.mark.usefixtures("_stub_installation")
async def test_submit_409_when_already_submitted(authenticated_client: AsyncClient) -> None:
    """Submitting an already-completed session is rejected (issue-040)."""
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_session(project_id, user_id, status="completed")
    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}/submit")
    assert resp.status_code == 409


async def test_save_answer_409_when_completed(authenticated_client: AsyncClient) -> None:
    """Editing answers after grading/completion is rejected (issue-040)."""
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_session(project_id, user_id, status="completed")
    resp = await authenticated_client.patch(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}/answers",
        json={"question_id": "q1", "value": "changed"},
    )
    assert resp.status_code == 409
