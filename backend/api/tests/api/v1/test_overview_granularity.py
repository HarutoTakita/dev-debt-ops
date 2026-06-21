"""api Overview granularity (issue 055): feature/folder rollup + feature drilldown + compat."""

import uuid

from httpx import AsyncClient

from app.core import db as app_db
from app.models.project import Project
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, CodeDebt, Feature, FeatureFile, FileKc


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


async def _seed(project_id: uuid.UUID) -> None:
    """KC run with two files (auth/a high, auth/b low) + a feature 'auth' over both."""
    async with app_db.async_session_maker() as session:
        kc_run = AnalysisRun(
            project_id=project_id, commit_sha="k", kind=JobType.KC_ANALYSIS.value, status=JobStatus.COMPLETED
        )
        feat_run = AnalysisRun(
            project_id=project_id, commit_sha="f", kind=JobType.FEATURE_CLUSTERING.value, status=JobStatus.COMPLETED
        )
        session.add_all([kc_run, feat_run])
        await session.flush()
        session.add_all(
            [
                FileKc(run_id=kc_run.id, file_path="src/auth/a.py", kc=0.9, mastery="star"),
                FileKc(run_id=kc_run.id, file_path="src/auth/b.py", kc=0.3, mastery="black_hole"),
            ]
        )
        feat = Feature(project_id=project_id, run_id=feat_run.id, key="auth", name="認証")
        session.add(feat)
        await session.flush()
        session.add_all(
            [
                FeatureFile(run_id=feat_run.id, feature_id=feat.id, file_path="src/auth/a.py", confidence=0.9),
                FeatureFile(run_id=feat_run.id, feature_id=feat.id, file_path="src/auth/b.py", confidence=0.9),
            ]
        )
        await session.commit()


async def test_default_granularity_is_file_backward_compatible(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed(project_id)
    body = (await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview")).json()
    assert body["granularity"] == "file"
    assert body["features"] == []
    assert {f["path"] for f in body["files"]} == {"src/auth/a.py", "src/auth/b.py"}


async def test_feature_granularity_rolls_up_kc(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed(project_id)
    body = (
        await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview?granularity=feature")
    ).json()
    assert body["granularity"] == "feature"
    assert len(body["features"]) == 1
    node = body["features"][0]
    assert node["key"] == "auth"
    assert node["name"] == "認証"
    assert node["knowledge_coverage"] == 0.6  # avg(0.9, 0.3)
    assert node["file_count"] == 2
    assert node["weakest_file"] == "src/auth/b.py"  # lowest KC


async def test_feature_rolls_up_code_debt_as_max(authenticated_client: AsyncClient) -> None:
    """Feature node code_debt_score = max over its files (issue 057 slice display + rollup)."""
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed(project_id)
    async with app_db.async_session_maker() as session:
        code_run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.CODE_DEBT_DETECTION.value, status=JobStatus.COMPLETED
        )
        session.add(code_run)
        await session.flush()
        session.add(
            CodeDebt(
                project_id=project_id,
                run_id=code_run.id,
                file_path="src/auth/a.py",
                type="complexity",
                severity="high",
                code_debt_score=0.8,
            )
        )
        await session.commit()

    body = (
        await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview?granularity=feature")
    ).json()
    node = body["features"][0]
    assert node["code_debt_score"] == 0.8  # max over auth/a (0.8) and auth/b (0.0)


async def test_folder_granularity_projects_directory(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed(project_id)
    body = (
        await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview?granularity=folder")
    ).json()
    folders = {f["key"]: f for f in body["features"]}
    assert "src/auth" in folders
    assert folders["src/auth"]["granularity"] == "folder"
    assert folders["src/auth"]["file_count"] == 2


async def test_invalid_granularity_422(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview?granularity=class")
    assert resp.status_code == 422


async def test_feature_drilldown_returns_files(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed(project_id)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/features/auth")
    assert resp.status_code == 200
    paths = {f["path"] for f in resp.json()}
    assert paths == {"src/auth/a.py", "src/auth/b.py"}

    # unknown feature → empty list.
    empty = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/features/nope")
    assert empty.status_code == 200
    assert empty.json() == []
