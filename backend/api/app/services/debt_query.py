"""Read/aggregation queries for Overview + debt registry delivery (issue 031).

Reads the rows that issues 028-030 persist (``code_debts`` / ``knowledge_debts`` /
``assigned_developers`` / ``file_kc``) plus the 031 ``debt_trend_points`` table, and shapes them
into the snake_case delivery schemas. No detection / scoring is done here beyond the priority
band (a tiny pure function mirrored from ``service.code_analysis.derive_priority`` since api must
not import the ``service`` package).
"""

import posixpath
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.project import Project
from app.schemas.debt import AssignedDeveloperOut, CodeDebtOut, DebtItemOut, DebtListOut, KnowledgeDebtOut
from app.schemas.overview import DebtTrendPointOut, FileDebtOut, OverviewOut, WeeklyActivityOut
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, AssignedDeveloper, CodeDebt, DebtTrendPoint, FileKc, KnowledgeDebt

SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}

_LANG_BY_EXT = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".svelte": "Svelte",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
}


def derive_priority(code: float, knowledge_coverage: float) -> str:
    """Two-axis priority P0–P3 (mirrors ``service.code_analysis.derive_priority``, issue 028)."""
    know = 1.0 - knowledge_coverage
    if code >= 0.6 and know >= 0.6:
        return "P0"
    if code >= 0.6 or know >= 0.6:
        return "P1"
    if code >= 0.3 or know >= 0.3:
        return "P2"
    return "P3"


def _language_of(path: str) -> str:
    return _LANG_BY_EXT.get(posixpath.splitext(path)[1].lower(), "Unknown")


async def _latest_run_id(session: AsyncSession, project_id: uuid.UUID, kind: JobType) -> uuid.UUID | None:
    run = (
        await session.execute(
            select(AnalysisRun)
            .where(
                col(AnalysisRun.project_id) == project_id,
                col(AnalysisRun.kind) == kind.value,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return run.id if run is not None else None


async def _assigned(session: AsyncSession, kind: str, debt_id: uuid.UUID) -> list[AssignedDeveloperOut]:
    rows = (
        (
            await session.execute(
                select(AssignedDeveloper).where(
                    col(AssignedDeveloper.debt_kind) == kind, col(AssignedDeveloper.debt_id) == debt_id
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        AssignedDeveloperOut(github_handle=r.github_handle, coverage=r.coverage, certified_via=r.certified_via)
        for r in rows
    ]


async def _code_out(session: AsyncSession, row: CodeDebt, repo: str) -> CodeDebtOut:
    return CodeDebtOut(
        id=str(row.id),
        file_path=row.file_path,
        repo=repo,
        type=row.type,
        severity=row.severity,
        status=row.status,
        detected_at=row.detected_at,
        related_pr=row.related_pr,
        related_adr=row.related_adr,
        archaeology_notes=row.archaeology_notes,
        code_snippet=row.code_snippet,
        code_debt_score=row.code_debt_score,
        knowledge_coverage=row.knowledge_coverage,
        ai_generation_prob=row.ai_generation_prob,
        estimated_repay_hours=row.estimated_repay_hours,
        assigned_developers=await _assigned(session, "code", row.id),
    )


async def _knowledge_out(session: AsyncSession, row: KnowledgeDebt) -> KnowledgeDebtOut:
    return KnowledgeDebtOut(
        id=str(row.id),
        file_path=row.file_path,
        repo=row.repo,
        reason=row.reason,
        severity=row.severity,
        status=row.status,
        detected_at=row.detected_at,
        related_adr=row.related_adr,
        code_snippet=row.code_snippet,
        code_debt_score=row.code_debt_score,
        knowledge_coverage=row.knowledge_coverage,
        ai_generation_prob=row.ai_generation_prob,
        estimated_repay_hours=row.estimated_repay_hours,
        assigned_developers=await _assigned(session, "knowledge", row.id),
    )


async def build_overview(session: AsyncSession, project: Project, org_slug: str) -> OverviewOut:
    """Aggregate the latest code-debt + KC runs into the Overview payload (empty when none)."""
    code_run = await _latest_run_id(session, project.id, JobType.CODE_DEBT_DETECTION)
    kc_run = await _latest_run_id(session, project.id, JobType.KC_ANALYSIS)

    code_score: dict[str, float] = {}
    pr_set: set[str] = set()
    merged = 0
    if code_run is not None:
        code_rows = (await session.execute(select(CodeDebt).where(col(CodeDebt.run_id) == code_run))).scalars().all()
        for r in code_rows:
            code_score[r.file_path] = max(code_score.get(r.file_path, 0.0), r.code_debt_score)
            if r.related_pr:
                pr_set.add(r.related_pr)
            if r.status in ("in_pr", "resolved"):
                merged += 1

    kc_map: dict[str, float] = {}
    if kc_run is not None:
        kc_rows = (
            (
                await session.execute(
                    select(FileKc).where(
                        col(FileKc.run_id) == kc_run,
                        col(FileKc.dev_id).is_(None),
                        col(FileKc.github_handle).is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for r in kc_rows:
            kc_map[r.file_path] = r.kc

    files = []
    for path in sorted(set(code_score) | set(kc_map)):
        code = code_score.get(path, 0.0)
        kc = kc_map.get(path, 0.0)
        files.append(
            FileDebtOut(
                path=path,
                language=_language_of(path),
                code_debt_score=code,
                knowledge_coverage=kc,
                business_impact=0.5,  # not yet captured (doc 008 §3); fixed placeholder
                priority=derive_priority(code, kc),
            )
        )

    trend_rows = (
        (await session.execute(select(DebtTrendPoint).where(col(DebtTrendPoint.project_id) == project.id)))
        .scalars()
        .all()
    )
    trend = sorted(
        (
            DebtTrendPointOut(week=t.week, code_debt_score=t.code_debt_score, knowledge_coverage=t.knowledge_coverage)
            for t in trend_rows
        ),
        key=lambda p: p.week,
    )

    activity = WeeklyActivityOut(
        code_agent_prs=len(pr_set),
        code_agent_merged=merged,
        knowledge_agent_quizzes=0,  # zero-filled until issue 034 (quiz_session)
        knowledge_agent_passed=0,
    )
    return OverviewOut(org=org_slug, generated_at=datetime.now(UTC), files=files, trend=trend, activity=activity)


async def list_debts(
    session: AsyncSession,
    project: Project,
    *,
    kinds: list[str] | None,
    severities: list[str] | None,
    statuses: list[str] | None,
    sort_key: str,
    sort_dir: str,
) -> DebtListOut:
    """List code + knowledge debts (latest runs) with filter/sort applied (``debtListSchema``)."""
    want_code = kinds is None or "code" in kinds
    want_knowledge = kinds is None or "knowledge" in kinds

    items: list[DebtItemOut] = []
    if want_code:
        code_run = await _latest_run_id(session, project.id, JobType.CODE_DEBT_DETECTION)
        if code_run is not None:
            stmt = select(CodeDebt).where(col(CodeDebt.run_id) == code_run)
            if severities:
                stmt = stmt.where(col(CodeDebt.severity).in_(severities))
            if statuses:
                stmt = stmt.where(col(CodeDebt.status).in_(statuses))
            for r in (await session.execute(stmt)).scalars().all():
                items.append(await _code_out(session, r, project.repo_name))
    if want_knowledge:
        kn_run = await _latest_run_id(session, project.id, JobType.KNOWLEDGE_DEBT_DETECTION)
        if kn_run is not None:
            stmt = select(KnowledgeDebt).where(col(KnowledgeDebt.run_id) == kn_run)
            if severities:
                stmt = stmt.where(col(KnowledgeDebt.severity).in_(severities))
            if statuses:
                stmt = stmt.where(col(KnowledgeDebt.status).in_(statuses))
            for r in (await session.execute(stmt)).scalars().all():
                items.append(await _knowledge_out(session, r))

    reverse = sort_dir != "asc"
    if sort_key == "severity":
        items.sort(key=lambda d: SEVERITY_RANK.get(d.severity, 0), reverse=reverse)
    elif sort_key == "estimated_repay_hours":
        items.sort(key=lambda d: d.estimated_repay_hours, reverse=reverse)
    else:  # detected_at
        items.sort(key=lambda d: d.detected_at, reverse=reverse)

    return DebtListOut(debts=items, total=len(items))


async def get_debt(session: AsyncSession, project: Project, debt_id: uuid.UUID) -> DebtItemOut | None:
    """Return one debt (code or knowledge) by id with assigned_developers joined, or None."""
    code = (
        await session.execute(
            select(CodeDebt).where(col(CodeDebt.id) == debt_id, col(CodeDebt.project_id) == project.id)
        )
    ).scalar_one_or_none()
    if code is not None:
        return await _code_out(session, code, project.repo_name)
    kn = (
        await session.execute(
            select(KnowledgeDebt).where(col(KnowledgeDebt.id) == debt_id, col(KnowledgeDebt.project_id) == project.id)
        )
    ).scalar_one_or_none()
    if kn is not None:
        return await _knowledge_out(session, kn)
    return None
