"""api knowledge-units (issue 063): feature-unit learn→confirm hub + learning plan feature_id."""

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1.github import resolve_installation_id
from app.core import db as app_db
from app.main import app
from app.models.project import Project
from app.services.dependencies import reset_blob_client, reset_task_dispatcher
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, FileKc, LearningPlan, QuizSession


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


async def test_knowledge_units_empty_without_clustering(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/knowledge-units")
    assert resp.status_code == 200
    assert resp.json() == {"units": []}


async def test_knowledge_units_joins_kc_plan_and_quiz(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, user_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        kc_run = AnalysisRun(
            project_id=project_id, commit_sha="k", kind=JobType.KC_ANALYSIS.value, status=JobStatus.COMPLETED
        )
        feat_run = AnalysisRun(
            project_id=project_id, commit_sha="f", kind=JobType.FEATURE_CLUSTERING.value, status=JobStatus.COMPLETED
        )
        session.add_all([kc_run, feat_run])
        await session.flush()
        # KC aggregate row (dev/handle null) so the 055 rollup reads kc=0.9 → star → verified.
        session.add(FileKc(run_id=kc_run.id, file_path="src/auth.py", kc=0.9, mastery="star"))
        feat = Feature(project_id=project_id, run_id=feat_run.id, key="auth", name="認証")
        session.add(feat)
        await session.flush()
        session.add(FeatureFile(run_id=feat_run.id, feature_id=feat.id, file_path="src/auth.py", confidence=0.9))
        plan = LearningPlan(project_id=project_id, developer_id=user_id, feature_id=feat.id, gap_concepts=["auth"])
        qs = QuizSession(
            project_id=project_id,
            developer_id=user_id,
            feature_id=feat.id,
            granularity="feature",
            file_path="src/auth.py",
            repo_full_name="acme/rosetta",
            status="completed",
            questions=[],
            answer_key={},
        )
        session.add_all([plan, qs])
        await session.commit()
        plan_id, qs_id = str(plan.id), str(qs.id)

    body = (await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/knowledge-units")).json()
    units = {u["feature_key"]: u for u in body["units"]}
    assert "auth" in units
    u = units["auth"]
    assert u["name"] == "認証"
    assert u["knowledge_coverage"] == 0.9
    assert u["file_count"] == 1
    assert u["learning_plan_id"] == plan_id
    assert u["quiz_session_id"] == qs_id
    assert u["quiz_status"] == "completed"
    assert u["status"] == "verified"  # kc >= 0.7


@pytest.mark.usefixtures("_stub_installation")
async def test_learning_plan_persists_feature_id(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _project_id, _ = await _seed_project(authenticated_client)
    feature_id = str(uuid.uuid4())
    resp = await authenticated_client.post(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/learning/plans",
        json={"gap_concepts": ["auth"], "feature_id": feature_id},
    )
    assert resp.status_code == 202
    plan_id = uuid.UUID(resp.json()["plan_id"])
    async with app_db.async_session_maker() as session:
        plan = await session.get(LearningPlan, plan_id)
        assert plan is not None
        assert str(plan.feature_id) == feature_id
