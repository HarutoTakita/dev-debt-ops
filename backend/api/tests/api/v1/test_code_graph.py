"""api code-graph delivery (issue 235): unobserved empty 200 + persisted snapshot projection."""

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient

from app.core import db as app_db
from app.models.project import Project
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, CodeGraph, Feature, FeatureFile


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


async def test_code_graph_unobserved_returns_empty(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is False
    assert body["file_edges"] == []


async def test_code_graph_returns_persisted_snapshot(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        session.add(
            CodeGraph(
                project_id=project_id,
                computed_at=datetime.now(UTC),
                graph={
                    "file_edges": [{"source": "pkg/main.py", "target": "pkg/util.py"}],
                    "functions": [
                        {"file": "pkg/util.py", "name": "helper"},
                        {"file": "pkg/util.py", "name": "inner"},
                        {"file": "pkg/main.py", "name": "main"},
                    ],
                    "function_calls": [{"file": "pkg/util.py", "source": "helper", "target": "inner"}],
                },
            )
        )
        await session.commit()
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is True
    assert body["file_edges"] == [{"source": "pkg/main.py", "target": "pkg/util.py"}]


async def test_code_graph_file_function_graph(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        session.add(
            CodeGraph(
                project_id=project_id,
                computed_at=datetime.now(UTC),
                graph={
                    "functions": [
                        {"file": "pkg/util.py", "name": "helper"},
                        {"file": "pkg/util.py", "name": "inner"},
                        {"file": "pkg/main.py", "name": "main"},
                    ],
                    "function_calls": [
                        {"file": "pkg/util.py", "source": "helper", "target": "inner"},
                        {"file": "pkg/main.py", "source": "main", "target": "x"},
                    ],
                },
            )
        )
        await session.commit()
    resp = await authenticated_client.get(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph/file", params={"path": "pkg/util.py"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is True
    assert {"id": "helper"} in body["nodes"]
    assert {"id": "main"} not in body["nodes"]  # 別ファイルの関数は含めない
    # 旧形 {file,...} の stale 行でも _call_files のフォールバックで L3 が壊れない（issue 282 後方互換）。
    assert body["edges"] == [{"source": "helper", "target": "inner"}]


async def test_file_function_graph_new_shape_excludes_cross_file(authenticated_client: AsyncClient) -> None:
    """issue 282: L3 (single file) shows only intra-file calls; cross-file calls are excluded here."""
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        session.add(
            CodeGraph(
                project_id=project_id,
                computed_at=datetime.now(UTC),
                graph={
                    "functions": [{"file": "pkg/util.py", "name": "helper"}, {"file": "pkg/util.py", "name": "inner"}],
                    "function_calls": [
                        {
                            "source_file": "pkg/util.py",
                            "source": "helper",
                            "target_file": "pkg/util.py",
                            "target": "inner",
                        },
                        {
                            "source_file": "pkg/util.py",
                            "source": "helper",
                            "target_file": "pkg/main.py",
                            "target": "main",
                        },
                    ],
                },
            )
        )
        await session.commit()
    resp = await authenticated_client.get(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph/file", params={"path": "pkg/util.py"}
    )
    body = resp.json()
    assert body["edges"] == [{"source": "helper", "target": "inner"}]  # cross-file (→pkg/main.py) excluded


async def _seed_feature_run(project_id: uuid.UUID, key: str, files: list[str]) -> None:
    """Seed a COMPLETED feature_clustering run with one feature owning ``files``."""
    async with app_db.async_session_maker() as session:
        run = AnalysisRun(
            project_id=project_id,
            commit_sha="abc",
            branch="main",
            kind=JobType.FEATURE_CLUSTERING.value,
            status=JobStatus.COMPLETED,
        )
        session.add(run)
        await session.flush()
        feature = Feature(
            project_id=project_id, run_id=run.id, key=key, name=key, source="ai", computed_at=datetime.now(UTC)
        )
        session.add(feature)
        await session.flush()
        for p in files:
            session.add(FeatureFile(run_id=run.id, feature_id=feature.id, file_path=p, confidence=1.0))
        await session.commit()


async def test_feature_function_graph(authenticated_client: AsyncClient) -> None:
    """issue 282: feature graph = file-hub + function nodes, CONTAINS + CALLS (incl. cross-file), scoped."""
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed_feature_run(project_id, "auth", ["pkg/a.py", "pkg/b.py"])
    async with app_db.async_session_maker() as session:
        session.add(
            CodeGraph(
                project_id=project_id,
                computed_at=datetime.now(UTC),
                graph={
                    "functions": [
                        {"file": "pkg/a.py", "name": "login"},
                        {"file": "pkg/b.py", "name": "verify"},
                        {"file": "pkg/other.py", "name": "unrelated"},  # outside the feature → excluded
                    ],
                    "function_calls": [
                        {"source_file": "pkg/a.py", "source": "login", "target_file": "pkg/b.py", "target": "verify"},
                    ],
                },
            )
        )
        await session.commit()
    resp = await authenticated_client.get(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph/feature", params={"key": "auth"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed"] is True
    assert body["truncated"] is False
    ids = {n["id"] for n in body["nodes"]}
    assert {"file::pkg/a.py", "pkg/a.py::login", "pkg/b.py::verify"} <= ids
    assert "pkg/other.py::unrelated" not in ids  # scoped to the feature's files
    kinds = {n["id"]: n["kind"] for n in body["nodes"]}
    assert kinds["file::pkg/a.py"] == "file"
    assert kinds["pkg/a.py::login"] == "function"
    # CONTAINS (hub → function) + the cross-file CALLS edge both present.
    assert {"source": "file::pkg/a.py", "target": "pkg/a.py::login", "type": "contains"} in body["edges"]
    assert {"source": "pkg/a.py::login", "target": "pkg/b.py::verify", "type": "calls"} in body["edges"]


async def test_feature_function_graph_unobserved_without_run(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        session.add(CodeGraph(project_id=project_id, computed_at=datetime.now(UTC), graph={"functions": []}))
        await session.commit()
    resp = await authenticated_client.get(
        f"/api/v1/orgs/{org_slug}/projects/{project_slug}/code-graph/feature", params={"key": "auth"}
    )
    assert resp.status_code == 200
    assert resp.json()["observed"] is False  # no feature_clustering run → unobserved
