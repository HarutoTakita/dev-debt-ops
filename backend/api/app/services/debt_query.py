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
from app.schemas.overview import DebtTrendPointOut, FeatureDebtOut, FileDebtOut, OverviewOut, WeeklyActivityOut
from shared.enums import JobStatus, JobType
from shared.models import (
    AnalysisRun,
    AssignedDeveloper,
    CodeDebt,
    DebtTrendPoint,
    Feature,
    FeatureFile,
    FileKc,
    KnowledgeDebt,
)

SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}

# 推移ブロックに表示する直近スナップショット数（issue 067, 解析ごとに 1 点）。
_TREND_LIMIT = 12

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


def _to_assigned_out(r: AssignedDeveloper) -> AssignedDeveloperOut:
    return AssignedDeveloperOut(github_handle=r.github_handle, coverage=r.coverage, certified_via=r.certified_via)


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
    return [_to_assigned_out(r) for r in rows]


async def _assigned_map(
    session: AsyncSession, kind: str, debt_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[AssignedDeveloperOut]]:
    """Load assignments for many debts in one query, grouped by debt id (issue-045: no N+1)."""
    if not debt_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(AssignedDeveloper).where(
                    col(AssignedDeveloper.debt_kind) == kind, col(AssignedDeveloper.debt_id).in_(debt_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[uuid.UUID, list[AssignedDeveloperOut]] = {}
    for r in rows:
        grouped.setdefault(r.debt_id, []).append(_to_assigned_out(r))
    return grouped


async def _code_out(
    session: AsyncSession, row: CodeDebt, repo: str, assigned: list[AssignedDeveloperOut] | None = None
) -> CodeDebtOut:
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
        assigned_developers=assigned if assigned is not None else await _assigned(session, "code", row.id),
    )


async def _knowledge_out(
    session: AsyncSession, row: KnowledgeDebt, assigned: list[AssignedDeveloperOut] | None = None
) -> KnowledgeDebtOut:
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
        assigned_developers=assigned if assigned is not None else await _assigned(session, "knowledge", row.id),
    )


def _empty_file_debt(path: str) -> FileDebtOut:
    """A file with no KC/code-debt data yet (analysed-clean / not-yet-covered) — used as a fallback."""
    return FileDebtOut(
        path=path,
        language=_language_of(path),
        code_debt_score=0.0,
        knowledge_coverage=0.0,
        business_impact=0.5,
        priority="P3",
    )


def _node_from_files(key: str, name: str, granularity: str, members: list[FileDebtOut]) -> FeatureDebtOut:
    """Roll up file-level points into one feature/folder node (issue 055, ADR 0006).

    ``knowledge_coverage`` = average over members (a mostly-understood node reads as understood);
    ``weakest_file`` = the lowest-KC member (the understanding-debt focus); ``code_debt_score`` =
    max over members (mirrors the file-level code aggregation, code rollup proper is issue 057).
    """
    code = max((f.code_debt_score for f in members), default=0.0)
    avg_kc = round(sum(f.knowledge_coverage for f in members) / len(members), 4) if members else 0.0
    weakest = min(members, key=lambda f: f.knowledge_coverage, default=None)
    return FeatureDebtOut(
        key=key,
        name=name,
        granularity=granularity,
        code_debt_score=code,
        knowledge_coverage=avg_kc,
        priority=derive_priority(code, avg_kc),
        file_count=len(members),
        weakest_file=weakest.path if weakest is not None else None,
    )


async def _rollup_features(
    session: AsyncSession, project: Project, by_path: dict[str, FileDebtOut], granularity: str
) -> list[FeatureDebtOut]:
    """Group file-level points into feature or folder nodes (issue 055)."""
    if granularity == "folder":
        groups: dict[str, list[FileDebtOut]] = {}
        for path, fd in by_path.items():
            groups.setdefault(posixpath.dirname(path) or "(root)", []).append(fd)
        return [_node_from_files(d, d, "folder", m) for d, m in sorted(groups.items())]

    # feature: roll up by the latest feature-clustering run's feature_files mapping.
    run_id = await _latest_run_id(session, project.id, JobType.FEATURE_CLUSTERING)
    if run_id is None:
        return []
    features = (await session.execute(select(Feature).where(col(Feature.run_id) == run_id))).scalars().all()
    members_by_feature = (
        (await session.execute(select(FeatureFile).where(col(FeatureFile.run_id) == run_id))).scalars().all()
    )
    paths_by_feature: dict[uuid.UUID, list[str]] = {}
    for ff in members_by_feature:
        paths_by_feature.setdefault(ff.feature_id, []).append(ff.file_path)
    nodes: list[FeatureDebtOut] = []
    for feat in features:
        members = [by_path.get(p, _empty_file_debt(p)) for p in paths_by_feature.get(feat.id, [])]
        nodes.append(_node_from_files(feat.key, feat.name, "feature", members))
    return nodes


async def build_feature_drilldown(session: AsyncSession, project: Project, feature_key: str) -> list[FileDebtOut]:
    """Return the file-level points for one feature (issue 055 drilldown). 404-empty if unknown."""
    run_id = await _latest_run_id(session, project.id, JobType.FEATURE_CLUSTERING)
    if run_id is None:
        return []
    feat = (
        await session.execute(select(Feature).where(col(Feature.run_id) == run_id, col(Feature.key) == feature_key))
    ).scalar_one_or_none()
    if feat is None:
        return []
    paths = [
        ff.file_path
        for ff in (await session.execute(select(FeatureFile).where(col(FeatureFile.feature_id) == feat.id)))
        .scalars()
        .all()
    ]
    overview = await build_overview(session, project, "", granularity="file")
    by_path = {f.path: f for f in overview.files}
    return [by_path.get(p, _empty_file_debt(p)) for p in paths]


async def build_overview(
    session: AsyncSession, project: Project, org_slug: str, *, granularity: str = "file"
) -> OverviewOut:
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

    # File universe for the scatter: drive off the KC run's files, not the union (issue-047).
    # The KC run scores *every* analysed source file, so each plotted point carries a real
    # knowledge_coverage. The code-debt run only persists threshold-crossing *findings*, so
    # unioning it in fabricates knowledge_coverage=0.0 for any flagged file the KC run didn't
    # cover (the two pipelines have different file caps) — those points then pile on the left
    # edge and the horizontal axis reads as binary. Falling back to the code-debt file set only
    # when no KC run exists yet keeps the dashboard non-empty during a KC-pending window
    # (those points sit at kc=0.0 = genuinely "unexplored", not a fabricated value).
    universe = sorted(kc_map) if kc_map else sorted(code_score)
    files = []
    for path in universe:
        code = code_score.get(path, 0.0)  # 0.0 = analysed & clean (KC files ⊆ code-debt files)
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
        (
            await session.execute(
                select(DebtTrendPoint)
                .where(col(DebtTrendPoint.project_id) == project.id)
                .order_by(col(DebtTrendPoint.created_at).desc())
                .limit(_TREND_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    trend = sorted(
        (
            DebtTrendPointOut(week=t.week, code_debt_score=t.code_debt_score, knowledge_coverage=t.knowledge_coverage)
            for t in trend_rows
        ),
        key=lambda p: p.week,  # ISO タイムスタンプ文字列なので辞書順 = 時系列順
    )

    activity = WeeklyActivityOut(
        code_agent_prs=len(pr_set),
        code_agent_merged=merged,
        knowledge_agent_quizzes=0,  # zero-filled until issue 034 (quiz_session)
        knowledge_agent_passed=0,
    )
    by_path = {f.path: f for f in files}
    features = await _rollup_features(session, project, by_path, granularity) if granularity != "file" else []
    return OverviewOut(
        org=org_slug,
        generated_at=datetime.now(UTC),
        granularity=granularity,
        files=files,
        features=features,
        trend=trend,
        activity=activity,
    )


def _snapshot_key() -> str:
    """Per-run snapshot key/label: the current UTC timestamp in ISO form (issue 067).

    One point is recorded per analysis run. Stored in the generic ``week`` column; ISO ordering is
    chronological and microsecond precision keeps successive runs distinct (the ``(project_id, week)``
    unique constraint effectively never collides; an exact-same-instant re-run merely upserts).
    """
    return datetime.now(UTC).isoformat()


async def record_trend_snapshot(
    session: AsyncSession, project: Project, org_slug: str = ""
) -> DebtTrendPointOut | None:
    """Append a trend point from the current project aggregates (issue 067).

    Records one point per analysis run (keyed by run timestamp) so the trend grows each time you
    analyse. Aggregates are the mean ``code_debt_score`` / mean ``knowledge_coverage`` over the
    analysed files. Returns ``None`` (records nothing) when nothing has been analysed yet.
    """
    overview = await build_overview(session, project, org_slug, granularity="file")
    files = overview.files
    if not files:
        return None
    n = len(files)
    code = sum(f.code_debt_score for f in files) / n
    kc = sum(f.knowledge_coverage for f in files) / n
    week = _snapshot_key()
    existing = (
        await session.execute(
            select(DebtTrendPoint).where(col(DebtTrendPoint.project_id) == project.id, col(DebtTrendPoint.week) == week)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.code_debt_score = code
        existing.knowledge_coverage = kc
        session.add(existing)
    else:
        session.add(
            DebtTrendPoint(
                project_id=project.id,
                week=week,
                code_debt_score=code,
                knowledge_coverage=kc,
                created_at=datetime.now(UTC),
            )
        )
    await session.commit()
    return DebtTrendPointOut(week=week, code_debt_score=code, knowledge_coverage=kc)


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
            code_rows = list((await session.execute(stmt)).scalars().all())
            amap = await _assigned_map(session, "code", [r.id for r in code_rows])
            for r in code_rows:
                items.append(await _code_out(session, r, project.repo_name, amap.get(r.id, [])))
    if want_knowledge:
        kn_run = await _latest_run_id(session, project.id, JobType.KNOWLEDGE_DEBT_DETECTION)
        if kn_run is not None:
            stmt = select(KnowledgeDebt).where(col(KnowledgeDebt.run_id) == kn_run)
            if severities:
                stmt = stmt.where(col(KnowledgeDebt.severity).in_(severities))
            if statuses:
                stmt = stmt.where(col(KnowledgeDebt.status).in_(statuses))
            kn_rows = list((await session.execute(stmt)).scalars().all())
            amap = await _assigned_map(session, "knowledge", [r.id for r in kn_rows])
            for r in kn_rows:
                items.append(await _knowledge_out(session, r, amap.get(r.id, [])))

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
