"""api quiz endpoints (issue 034): generate/list/get/answer/submit/result + authz.

The generation/grading pipelines run in service; api creates the session, enqueues, serves, and
strips the answer key. Installation id is stubbed; the mock dispatcher is reset.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1.github import resolve_installation_id, resolve_installation_id_optional
from app.core import db as app_db
from app.main import app
from app.models.project import Project
from app.services.dependencies import get_task_dispatcher, reset_blob_client, reset_task_dispatcher
from shared.enums import JobType
from shared.models import QuizAnswer, QuizResult, QuizSession


@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_task_dispatcher()
    reset_blob_client()
    yield
    reset_task_dispatcher()
    reset_blob_client()


@pytest.fixture
def _stub_installation():
    # submit_quiz uses the optional variant (returns None for demo); other routes use the strict one.
    app.dependency_overrides[resolve_installation_id] = lambda: 12345678
    app.dependency_overrides[resolve_installation_id_optional] = lambda: 12345678
    yield 12345678
    app.dependency_overrides.pop(resolve_installation_id, None)
    app.dependency_overrides.pop(resolve_installation_id_optional, None)


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


async def test_result_includes_per_question_review(authenticated_client: AsyncClient) -> None:
    """#4 誤答チェック: result exposes each question's your-answer vs correct-answer + correctness."""
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    async with app_db.async_session_maker() as session:
        qs = QuizSession(
            project_id=project_id,
            developer_id=user_id,
            file_path="src/a.py",
            repo_full_name="acme/rosetta",
            status="completed",
            questions=[
                {
                    "id": "q1",
                    "kind": "multiple_choice",
                    "prompt": "Q1?",
                    "choices": [{"id": "a", "label": "Alpha"}, {"id": "b", "label": "Beta"}],
                },
                {
                    "id": "q2",
                    "kind": "multiple_choice",
                    "prompt": "Q2?",
                    "choices": [{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}],
                },
            ],
            answer_key={"q1": {"answer": "a"}, "q2": {"answer": "b"}},
        )
        session.add(qs)
        await session.flush()
        sid = qs.id
        session.add_all(
            [
                QuizAnswer(session_id=sid, question_id="q1", value="a", is_correct=True),
                QuizAnswer(session_id=sid, question_id="q2", value="a", is_correct=False),
            ]
        )
        session.add(QuizResult(session_id=sid, understood=[], gap_concepts=[], kc_before=0.1, kc_after=0.5))
        await session.commit()

    body = (
        await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}/result")
    ).json()
    review = {r["question_id"]: r for r in body["review"]}
    assert review["q1"]["is_correct"] is True
    assert review["q2"]["is_correct"] is False
    assert review["q2"]["your_answer"] == "Yes"  # value "a" → label
    assert review["q2"]["correct_answer"] == "No"  # answer "b" → label


async def _seed_graded_mc(project_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    """Seed a completed 2-question MC session: q1 correct, q2 wrong (graded)."""
    async with app_db.async_session_maker() as session:
        qs = QuizSession(
            project_id=project_id,
            developer_id=user_id,
            file_path="src/a.py",
            repo_full_name="acme/rosetta",
            status="completed",
            questions=[
                {"id": "q1", "kind": "multiple_choice", "prompt": "Q1?", "choices": [{"id": "a", "label": "A"}]},
                {"id": "q2", "kind": "multiple_choice", "prompt": "Q2?", "choices": [{"id": "b", "label": "B"}]},
            ],
            answer_key={"q1": {"answer": "a"}, "q2": {"answer": "b"}},
        )
        session.add(qs)
        await session.flush()
        sid = qs.id
        session.add_all(
            [
                QuizAnswer(session_id=sid, question_id="q1", value="a", is_correct=True),
                QuizAnswer(session_id=sid, question_id="q2", value="a", is_correct=False),
            ]
        )
        await session.commit()
        return sid


async def test_flag_question_reflected_in_session(authenticated_client: AsyncClient) -> None:
    """#6: flagging a question surfaces it in the session's flagged_question_ids; clearing removes it."""
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_session(project_id, user_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}"
    assert (await authenticated_client.put(f"{base}/questions/q1/flag", json={"flagged": True})).status_code == 204
    # idempotent
    assert (await authenticated_client.put(f"{base}/questions/q1/flag", json={"flagged": True})).status_code == 204
    body = (await authenticated_client.get(base)).json()
    assert body["flagged_question_ids"] == ["q1"]
    assert (await authenticated_client.put(f"{base}/questions/q1/flag", json={"flagged": False})).status_code == 204
    assert (await authenticated_client.get(base)).json()["flagged_question_ids"] == []


async def test_retest_wrong_only_copies_incorrect_questions(authenticated_client: AsyncClient) -> None:
    """#6: retest mode=wrong creates a new session with only the all-attempts-wrong questions."""
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_graded_mc(project_id, user_id)
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}/retest", json={"mode": "wrong"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["question_count"] == 1
    async with app_db.async_session_maker() as session:
        retest = await session.get(QuizSession, uuid.UUID(data["session_id"]))
        assert [q["id"] for q in retest.questions] == ["q2"]  # only the wrong one
        assert retest.status == "not_started"
        assert retest.origin_session_id == sid
        assert retest.retest_mode == "wrong"
        assert set(retest.answer_key.keys()) == {"q2"}


async def test_retest_flagged_only_and_empty_is_400(authenticated_client: AsyncClient) -> None:
    """#6: retest mode=flagged uses flagged questions; an empty subset is a 400."""
    org_slug, project_slug, project_id, user_id = await _project(authenticated_client)
    sid = await _seed_graded_mc(project_id, user_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/quizzes/{sid}"
    # nothing flagged yet → 400
    assert (await authenticated_client.post(f"{base}/retest", json={"mode": "flagged"})).status_code == 400
    await authenticated_client.put(f"{base}/questions/q1/flag", json={"flagged": True})
    resp = await authenticated_client.post(f"{base}/retest", json={"mode": "flagged"})
    assert resp.status_code == 201
    assert resp.json()["question_count"] == 1
    async with app_db.async_session_maker() as session:
        retest = await session.get(QuizSession, uuid.UUID(resp.json()["session_id"]))
        assert [q["id"] for q in retest.questions] == ["q1"]


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
