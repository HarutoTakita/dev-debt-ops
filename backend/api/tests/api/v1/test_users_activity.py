"""Admin activity dashboard: ``GET /api/v1/users/activity`` (superuser only).

Verifies access control (superuser 200 / general 403) and that the per-member aggregates reflect
seeded learning / quiz / repayment-PR / issue rows attributed to a user.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.auth_demo import router as _demo_router
from app.core import db as app_db
from app.core.config import settings
from app.main import app

# DEMO_MODE_ENABLED is false in tests, so auth.py does not mount the demo router. Mount it here
# (idempotently) so the demo-user activity test can log in — mirrors test_demo_auth.py.
if not any(getattr(r, "path", None) == "/api/v1/auth/demo" for r in app.routes):
    app.include_router(_demo_router, prefix="/api/v1/auth")
from shared.enums import JobStatus, JobType
from shared.models import (
    AnalysisRun,
    CodeDebt,
    Job,
    LearningPlan,
    LearningResource,
    LearningStep,
    QuizSession,
)


async def _login_admin(email: str) -> AsyncClient:
    """Register + login a user whose email is in ADMIN_EMAILS → auto-promoted to superuser on login."""
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await client.post("/api/v1/auth/register", json={"email": email, "password": "testpassword123"})
    resp = await client.post("/api/v1/auth/login", data={"username": email, "password": "testpassword123"})
    client.cookies = resp.cookies
    return client


async def _seed_activity(user_id: uuid.UUID) -> None:
    """Attribute one of each metric-producing row to ``user_id`` (learning / quiz / PR job / issue)."""
    project_id = uuid.uuid4()
    async with app_db.async_session_maker() as s:
        # Learning: 1 plan with 2 steps (1 completed).
        plan = LearningPlan(project_id=project_id, developer_id=user_id, gap_concepts=[], estimated_total_minutes=10)
        s.add(plan)
        resource = LearningResource(
            project_id=project_id, origin="team", section="code", kind="code", title="読む", priority="required"
        )
        s.add(resource)
        await s.flush()  # need plan.id / resource.id for the steps' FKs
        s.add(LearningStep(plan_id=plan.id, order=0, completed=True, resource_id=resource.id))
        s.add(LearningStep(plan_id=plan.id, order=1, completed=False, resource_id=resource.id))

        # Quiz: 1 completed (score 0.8) + 1 not_started → total 2, completed 1, avg 0.8.
        s.add(QuizSession(project_id=project_id, developer_id=user_id, file_path="a.py", status="completed", score=0.8))
        s.add(QuizSession(project_id=project_id, developer_id=user_id, file_path="b.py", status="not_started"))

        # Code-quality engagement: 1 repayment-PR job + 1 issue-attributed code debt.
        s.add(Job(job_type=JobType.REPAYMENT_PR_GENERATION, status=JobStatus.COMPLETED, created_by=user_id, payload={}))
        run = AnalysisRun(
            project_id=project_id,
            commit_sha="deadbeef",
            branch="main",
            kind=JobType.CODE_DEBT_DETECTION.value,
            status=JobStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        s.add(run)
        await s.flush()  # need run.id for the debt's FK
        s.add(
            CodeDebt(
                project_id=project_id,
                run_id=run.id,
                file_path="a.py",
                type="complexity",
                severity="high",
                code_debt_score=0.8,
                related_issue="https://github.com/x/y/issues/1",
                related_issue_by=user_id,
            )
        )
        await s.commit()


async def test_activity_reports_member_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@example.com")
    client = await _login_admin("boss@example.com")
    try:
        me = (await client.get("/api/v1/users/me")).json()
        await _seed_activity(uuid.UUID(me["id"]))

        resp = await client.get("/api/v1/users/activity")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        mine = next(r for r in rows if r["id"] == me["id"])

        assert mine["learning_steps_total"] == 2
        assert mine["learning_steps_completed"] == 1
        assert mine["learning_plans_count"] == 1
        assert mine["quiz_total"] == 2
        assert mine["quiz_completed"] == 1
        assert mine["quiz_avg_score"] == pytest.approx(0.8)
        assert mine["pr_count"] == 1
        assert mine["issue_count"] == 1
    finally:
        await client.aclose()


async def test_activity_forbidden_for_general_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "")  # nobody is admin
    client = await _login_admin("plain@example.com")
    try:
        me = (await client.get("/api/v1/users/me")).json()
        assert me["is_superuser"] is False
        assert (await client.get("/api/v1/users/activity")).status_code == 403
    finally:
        await client.aclose()


async def test_activity_demo_user_sees_fabricated_members() -> None:
    """The guest-demo user can open the admin dashboard and gets fabricated sample members only.

    Demo is not a superuser but is allowed in to showcase the management UI — the rows are synthetic
    (all @sample-shop.demo), so no real account data is ever exposed to a guest.
    """
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        resp = await client.post("/api/v1/auth/demo")
        client.cookies = resp.cookies

        activity = await client.get("/api/v1/users/activity")
        assert activity.status_code == 200, activity.text
        rows = activity.json()
        assert len(rows) >= 5
        # Every returned member is fabricated demo data (no real accounts leaked).
        assert all(r["email"].endswith("@sample-shop.demo") for r in rows)
        # The metrics the dashboard renders are present and varied.
        assert any(r["pr_count"] > 0 for r in rows)
        assert any(r["quiz_avg_score"] is not None for r in rows)
    finally:
        await client.aclose()
