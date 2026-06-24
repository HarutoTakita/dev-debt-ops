"""api Overview aggregation + debt registry delivery (issue 031).

Seeds analysis_runs + code_debts / knowledge_debts / assigned_developers / file_kc, then asserts
the snake_case delivery shape, filter/sort, detail join, PATCH (dismiss + kind status validation),
and empty-state 200s.
"""

import uuid

from httpx import AsyncClient

from app.core import db as app_db
from app.models.project import Project
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, AssignedDeveloper, CodeDebt, FileKc, KnowledgeDebt


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


async def _seed_analysis(project_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed COMPLETED code / kc / knowledge runs with one debt each. Returns (code_id, knowledge_id)."""
    async with app_db.async_session_maker() as session:
        code_run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.CODE_DEBT_DETECTION.value, status=JobStatus.COMPLETED
        )
        kc_run = AnalysisRun(
            project_id=project_id, commit_sha="k", kind=JobType.KC_ANALYSIS.value, status=JobStatus.COMPLETED
        )
        kn_run = AnalysisRun(
            project_id=project_id,
            commit_sha="n",
            kind=JobType.KNOWLEDGE_DEBT_DETECTION.value,
            status=JobStatus.COMPLETED,
        )
        session.add_all([code_run, kc_run, kn_run])
        await session.flush()

        code = CodeDebt(
            project_id=project_id,
            run_id=code_run.id,
            file_path="src/a.py",
            type="complexity",
            severity="high",
            code_debt_score=0.8,
            related_pr="https://github.com/acme/rosetta/pull/1",
            status="in_pr",
        )
        kn = KnowledgeDebt(
            project_id=project_id,
            run_id=kn_run.id,
            file_path="src/b.py",
            repo="rosetta",
            reason="ai_generated",
            severity="critical",
            code_debt_score=0.9,
            ai_generation_prob=0.95,
        )
        session.add_all([code, kn])
        session.add(FileKc(run_id=kc_run.id, file_path="src/a.py", kc=0.3, mastery="black_hole"))  # aggregate
        await session.flush()
        session.add(
            AssignedDeveloper(
                debt_kind="knowledge", debt_id=kn.id, github_handle="carol", coverage=0.75, certified_via="authorship"
            )
        )
        await session.commit()
        return code.id, kn.id


async def test_overview_empty_returns_200(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, _ = await _seed_project(authenticated_client)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["org"] == org_slug
    assert body["files"] == []
    assert body["trend"] == []
    assert body["activity"] == {
        "code_agent_prs": 0,
        "code_agent_merged": 0,
        "knowledge_agent_quizzes": 0,
        "knowledge_agent_passed": 0,
    }


async def test_overview_aggregates_files(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed_analysis(project_id)
    resp = await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview")
    assert resp.status_code == 200
    body = resp.json()
    files = {f["path"]: f for f in body["files"]}
    assert files["src/a.py"]["code_debt_score"] == 0.8
    assert files["src/a.py"]["knowledge_coverage"] == 0.3
    assert files["src/a.py"]["priority"] == "P0"  # code 0.8 & know 0.7 both high
    assert files["src/a.py"]["language"] == "Python"
    assert body["activity"]["code_agent_prs"] == 1  # one related_pr
    assert body["activity"]["code_agent_merged"] == 1  # status in_pr


async def test_overview_universe_is_kc_set(authenticated_client: AsyncClient) -> None:
    """The scatter is driven off the KC file set, not the code∪kc union (issue-047).

    A code-debt finding with no KC row must NOT be plotted at knowledge_coverage=0.0 (the old
    left-edge artifact); a KC file with no code finding must appear at code_debt_score=0.0.
    """
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    async with app_db.async_session_maker() as session:
        code_run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.CODE_DEBT_DETECTION.value, status=JobStatus.COMPLETED
        )
        kc_run = AnalysisRun(
            project_id=project_id, commit_sha="k", kind=JobType.KC_ANALYSIS.value, status=JobStatus.COMPLETED
        )
        session.add_all([code_run, kc_run])
        await session.flush()
        session.add_all(
            [
                # flagged-but-no-KC: previously fabricated kc=0.0 and stuck to the left edge.
                CodeDebt(
                    project_id=project_id,
                    run_id=code_run.id,
                    file_path="src/flagged.py",
                    type="complexity",
                    severity="high",
                    code_debt_score=0.7,
                ),
                # known: both a code finding and a KC row → a real two-axis point.
                CodeDebt(
                    project_id=project_id,
                    run_id=code_run.id,
                    file_path="src/known.py",
                    type="complexity",
                    severity="critical",
                    code_debt_score=0.9,
                ),
                FileKc(run_id=kc_run.id, file_path="src/clean.py", kc=0.5, mastery="dim_star"),
                FileKc(run_id=kc_run.id, file_path="src/known.py", kc=0.2, mastery="black_hole"),
            ]
        )
        await session.commit()

    body = (await authenticated_client.get(f"/api/v1/orgs/{org_slug}/projects/{project_slug}/overview")).json()
    files = {f["path"]: f for f in body["files"]}

    assert set(files) == {"src/clean.py", "src/known.py"}  # universe = KC set; flagged.py excluded
    assert files["src/clean.py"] == {**files["src/clean.py"], "code_debt_score": 0.0, "knowledge_coverage": 0.5}
    assert files["src/known.py"] == {**files["src/known.py"], "code_debt_score": 0.9, "knowledge_coverage": 0.2}


async def test_list_debts_filter_and_sort(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed_analysis(project_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/debts"

    # No filter: both debts, severity desc → critical (knowledge) before high (code).
    res = (await authenticated_client.get(base)).json()
    assert res["total"] == 2
    assert res["debts"][0]["kind"] == "knowledge"
    assert res["debts"][0]["assigned_agent"] == "knowledge_debt"

    # kind filter.
    res = (await authenticated_client.get(f"{base}?kind=code")).json()
    assert res["total"] == 1
    assert res["debts"][0]["kind"] == "code"
    assert res["debts"][0]["repo"] == "rosetta"

    # severity filter.
    res = (await authenticated_client.get(f"{base}?severity=critical")).json()
    assert res["total"] == 1
    assert res["debts"][0]["severity"] == "critical"


async def test_get_debt_detail_and_404(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    _, kn_id = await _seed_analysis(project_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/debts"

    res = await authenticated_client.get(f"{base}/{kn_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "knowledge"
    assert body["assigned_developers"][0]["github_handle"] == "carol"
    assert body["assigned_developers"][0]["certified_via"] == "authorship"

    assert (await authenticated_client.get(f"{base}/{uuid.uuid4()}")).status_code == 404


async def test_patch_dismiss_code_and_reject_knowledge_dismissed(authenticated_client: AsyncClient) -> None:
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    code_id, kn_id = await _seed_analysis(project_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}/debts"

    res = await authenticated_client.patch(f"{base}/{code_id}", json={"status": "dismissed"})
    assert res.status_code == 200
    assert res.json()["status"] == "dismissed"

    # knowledge debts have no "dismissed" status → 422.
    res = await authenticated_client.patch(f"{base}/{kn_id}", json={"status": "dismissed"})
    assert res.status_code == 422


async def test_trend_snapshot_appends_per_run(authenticated_client: AsyncClient) -> None:
    """POST trend-snapshot records the averaged code/KC point; each run appends a new point (issue 067)."""
    org_slug, project_slug, project_id = await _seed_project(authenticated_client)
    await _seed_analysis(project_id)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}"

    # Universe = KC set = {src/a.py}: code 0.8 / kc 0.3 → averages are those single values.
    res = await authenticated_client.post(f"{base}/trend-snapshot")
    assert res.status_code == 200
    point = res.json()
    assert point["code_debt_score"] == 0.8
    assert point["knowledge_coverage"] == 0.3
    assert point["week"]  # non-empty ISO timestamp label

    body = (await authenticated_client.get(f"{base}/overview")).json()
    assert len(body["trend"]) == 1

    # One point per analysis run → a second run appends another point (not an upsert).
    assert (await authenticated_client.post(f"{base}/trend-snapshot")).status_code == 200
    body = (await authenticated_client.get(f"{base}/overview")).json()
    assert len(body["trend"]) == 2


async def test_trend_snapshot_noop_when_unanalysed(authenticated_client: AsyncClient) -> None:
    """No files analysed → no snapshot recorded (returns null, trend stays empty)."""
    org_slug, project_slug, _ = await _seed_project(authenticated_client)
    base = f"/api/v1/orgs/{org_slug}/projects/{project_slug}"
    res = await authenticated_client.post(f"{base}/trend-snapshot")
    assert res.status_code == 200
    assert res.json() is None
    body = (await authenticated_client.get(f"{base}/overview")).json()
    assert body["trend"] == []
