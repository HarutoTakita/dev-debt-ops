"""api Galaxy personal-KC delivery + analyze-galaxy enqueue (issue 032).

Seeds a kc_analysis run with file_kc (aggregate + this-developer dev rows) and dependencies, then
asserts the personalGalaxySchema projection (per-file dev KC, module systems, wormholes with the
``from`` key), the empty/unobserved 200, and the analyze-galaxy 202 enqueue.
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
from shared.models import AnalysisRun, Dependency, Feature, FeatureFile, FileKc, Job


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


async def _seed_kc(project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    async with app_db.async_session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="k", kind=JobType.KC_ANALYSIS.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        session.add_all(
            [
                # File universe = aggregate rows (dev_id None, handle None).
                FileKc(run_id=run.id, file_path="auth/login.py", kc=0.9, mastery="star"),
                FileKc(run_id=run.id, file_path="auth/token.py", kc=0.5, mastery="dim_star"),
                # This developer's KC(file,dev) for login.py only → token.py is unexplored for them.
                FileKc(
                    run_id=run.id,
                    file_path="auth/login.py",
                    dev_id=user_id,
                    github_handle="me-handle",
                    kc=0.8,
                    mastery="star",
                    certified_via="authorship",
                ),
                Dependency(run_id=run.id, from_path="auth/login.py", to_path="auth/token.py"),
            ]
        )
        await session.commit()


async def _seed_feature_run(project_id: uuid.UUID, key: str, name: str, file_paths: list[str]) -> None:
    async with app_db.async_session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="f", kind=JobType.FEATURE_CLUSTERING.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        feat = Feature(project_id=project_id, run_id=run.id, key=key, name=name)
        session.add(feat)
        await session.flush()
        session.add_all(
            [FeatureFile(run_id=run.id, feature_id=feat.id, file_path=p, confidence=0.9) for p in file_paths]
        )
        await session.commit()


async def test_galaxy_unobserved_returns_200(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/galaxy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is False
    assert body["systems"] == []
    assert body["wormholes"] == []


async def test_galaxy_projects_personal_kc(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id, user_id = await _seed_project(authenticated_client)
    await _seed_kc(project_id, user_id)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/galaxy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is True
    assert body["developer"] == "me-handle"
    assert body["org_kc"] == 0.65  # mean(0.8 login dev-KC, 0.5 token team-KC fallback)

    systems = {s["module"]: s for s in body["systems"]}
    auth = systems["auth"]
    files = {f["path"]: f for f in auth["files"]}
    assert files["auth/login.py"]["kc"] == 0.8  # this developer's KC(file,dev)
    assert files["auth/login.py"]["mastery"] == "star"
    assert files["auth/login.py"]["mastered"] is True
    # Untouched by this dev → falls back to the aggregate (team) KC/mastery instead of grey unexplored,
    # so node colors reflect the codebase even when the viewer didn't author the file.
    assert files["auth/token.py"]["kc"] == 0.5
    assert files["auth/token.py"]["mastery"] == "dim_star"
    assert auth["kc"] == 0.65  # mean of the two files' KC (dev for login, team fallback for token)

    assert body["wormholes"] == [{"from": "auth/login.py", "to": "auth/token.py"}]


async def test_galaxy_renders_feature_files_missing_from_kc(authenticated_client: AsyncClient) -> None:
    """機能に割り当てたファイルが KC 実行の採点集合に無くても、ノードとして必ず描画される（union）。

    従来は KC 実行の FileKc からしかノードを作らず、FC 実行だけが持つファイルは表示されなかった
    （チップは file_count>0 なのにマップは空＝「表示するファイルがありません」）。
    """
    org_slug, project_slug, project_id, user_id = await _seed_project(authenticated_client)
    await _seed_kc(project_id, user_id)  # KC は auth/login.py・auth/token.py のみ採点
    await _seed_feature_run(project_id, "auth", "認証", ["auth/login.py", "unscored/util.py"])

    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/galaxy")
    assert resp.status_code == 200
    body = resp.json()
    files = {f["path"]: f for s in body["systems"] for f in s["files"]}

    assert "unscored/util.py" in files  # KC 未採点でもノード化
    assert files["unscored/util.py"]["mastery"] == "unexplored"  # 未採点は unexplored 既定
    assert files["unscored/util.py"]["feature_keys"] == ["auth"]  # 機能タグが付く＝フィルタで拾える
    assert files["auth/login.py"]["feature_keys"] == ["auth"]

    feats = {f["key"]: f for f in body["features"]}
    assert feats["auth"]["file_count"] == 2  # 両方カウント（空チップにならない）
    assert body["org_kc"] == 0.65  # 未採点の既定 0 は org_kc に含めない（採点済みのみ平均）


@pytest.mark.usefixtures("_stub_installation")
async def test_analyze_galaxy_enqueues_kc_analysis(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.post(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/analyze-galaxy")
    assert resp.status_code == 202
    job_id = uuid.UUID(resp.json()["job_id"])

    async with app_db.async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.job_type == JobType.KC_ANALYSIS

    dispatcher = get_task_dispatcher()
    assert len(dispatcher.tasks) == 1
    assert dispatcher.tasks[0].pipeline == JobType.KC_ANALYSIS.value
