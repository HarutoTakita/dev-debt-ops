"""kc-analysis pipeline (issue 029) — compute Knowledge Coverage from git authorship/blame.

Fetches a repository snapshot via ``GitHubGitClient`` (method B token), derives KC(file,dev) from
blame line-share (027 authorship matching → ``users.id``), aggregates KC(file), applies the mastery
thresholds, extracts intra-repo dependency edges (wormholes), and upserts ``file_kc`` / ``dependencies``
under an ``analysis_run``. ``shared.worker.run_task`` owns the Job lifecycle + ``result_data``.

KC formula is an MVP: KC(file,dev) = the developer's blame line-share (``certified_via="authorship"``),
*capped at ``_AUTHORSHIP_KC_CEILING`` (below the ``dim_star`` threshold) so authorship alone maps to
**``black_hole`` = 未理解, not "understood"*** — authoring a file is *contact*, not verified mastery, and
understanding is meant to be **measured by quizzes**, not inferred from blame (product premise / issue-048).
Otherwise every authored file reads as teal ("理解済み") and the map looks done before any quiz is taken.
half-life / decay are unknown (no spec in repo) and intentionally omitted. KC(file) aggregate = max of dev
KCs. See ADR ``docs/adr/0003-kc-mastery-thresholds.md``. quiz-certified KC (034) updates rows later
(uncapped → can reach ``dim_star`` / ``star``) — this pipeline writes the ``certified_via`` column and
upsert path it will reuse.

Idempotent across at-least-once redelivery: the run is keyed by ``job_id`` and rows upsert on their
unique constraints (dev rows on ``(run_id, file_path, dev_id)``; aggregate rows on the partial index
``(run_id, file_path) WHERE dev_id IS NULL``).
"""

import logging
import posixpath
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services.authorship import AuthorIdentity, resolve_author_user_id
from service.services.code_analysis import is_vendored_path
from service.services.dependency_extraction import extract_dependencies
from service.services.github_app import GitHubAppService
from service.services.github_git_client import BlameRange, GitHubGitClient
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, Dependency, FileKc
from shared.pipelines.context import PipelineContext
from shared.schemas.kc_analysis import KcAnalysisRequest, KcAnalysisResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_MAX_FILES = 200  # blame is a GraphQL call per file; cap per run (aligned with feature_clustering)
# 対象拡張子。Python / TS・JS に加えフロントの .svelte / .vue も含める（理解度マップに Python 以外も出す）。
_SOURCE_EXTS = (".py", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".svelte", ".vue")

# Authorship is evidence of *contact*, not verified mastery. Cap authorship-derived KC **below the
# ``dim_star`` threshold (0.4)** so "I wrote it" maps to ``black_hole`` (未理解), never teal — otherwise
# a repo's dominant author makes almost every file read as understood before any quiz, and the map looks
# "done". Understanding is measured by quizzes: verified KC (quiz/review, issue 034) writes uncapped rows
# and can reach ``dim_star`` / ``star``. (issue-048 revisited)
_AUTHORSHIP_KC_CEILING = 0.35


async def _mint_installation_token(github: GitHubRef) -> str:
    """Method B: explicit access_token if present, else mint from the Secret Manager key."""
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


def _is_source(path: str) -> bool:
    return path.lower().endswith(_SOURCE_EXTS) and not is_vendored_path(path)


def _language_bucket(path: str) -> str:
    """Coarse language bucket for fair selection (so one language doesn't starve the cap)."""
    p = path.lower()
    if p.endswith(".py"):
        return "python"
    if p.endswith(".svelte"):
        return "svelte"
    if p.endswith(".vue"):
        return "vue"
    return "ts_js"


def _select_source_paths(paths: list[str], limit: int) -> list[str]:
    """Pick up to ``limit`` files, round-robin across language buckets.

    A plain ``sorted()[:limit]`` truncation starves later languages: if Python files sort first, the
    cap is exhausted by ``.py`` and no ``.ts`` / ``.svelte`` files survive → the理解度マップに Python
    しか出ない。Round-robin across buckets keeps the mix representative when the repo exceeds the cap.
    """
    buckets: dict[str, list[str]] = {}
    for p in paths:
        buckets.setdefault(_language_bucket(p), []).append(p)
    for b in buckets.values():
        b.sort()
    order = sorted(buckets)  # deterministic bucket order
    out: list[str] = []
    idx = 0
    while len(out) < limit and any(buckets[b] for b in order):
        bucket = buckets[order[idx % len(order)]]
        if bucket:
            out.append(bucket.pop(0))
        idx += 1
    return out


def _module_of(path: str) -> str:
    """Star-system = the file's directory (``fileMasterySchema.module``)."""
    parent = posixpath.dirname(path)
    return parent or "(root)"


def mastery_from_kc(kc: float, *, has_contact: bool) -> str:
    """Map KC ∈ [0,1] to a mastery status (issue 029 / doc 009 thresholds).

    ``star ≥ 0.7`` / ``dim_star 0.4–0.7`` / ``black_hole < 0.4 with contact`` / ``unexplored`` (no contact).
    """
    if not has_contact:
        return "unexplored"
    if kc >= 0.7:
        return "star"
    if kc >= 0.4:
        return "dim_star"
    return "black_hole"


def aggregate_blame(ranges: list[BlameRange]) -> list[tuple[AuthorIdentity, float]]:
    """Return ``(author, line_share)`` per author from blame ranges (line-share is KC(file,dev) MVP)."""
    total = sum(r.end_line - r.start_line + 1 for r in ranges)
    if total <= 0:
        return []
    lines: dict[tuple, int] = {}
    identities: dict[tuple, AuthorIdentity] = {}
    for r in ranges:
        key = (r.author_id, r.author_login, r.author_email)
        lines[key] = lines.get(key, 0) + (r.end_line - r.start_line + 1)
        identities[key] = AuthorIdentity(login=r.author_login, email=r.author_email, github_user_id=r.author_id)
    return [(identities[key], min(1.0, lines[key] / total)) for key in lines]


async def _get_or_create_run(
    session: AsyncSession, *, job_id: uuid.UUID, project_id: uuid.UUID, commit_sha: str, branch: str
) -> AnalysisRun:
    existing = (
        await session.execute(
            select(AnalysisRun).where(
                col(AnalysisRun.job_id) == job_id,
                col(AnalysisRun.kind) == JobType.KC_ANALYSIS.value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    run = AnalysisRun(
        project_id=project_id,
        commit_sha=commit_sha,
        branch=branch,
        kind=JobType.KC_ANALYSIS.value,
        job_id=job_id,
        status=JobStatus.PROCESSING,
    )
    session.add(run)
    await session.flush()
    return run


async def _upsert_file_kc(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    file_path: str,
    module: str,
    dev_id: uuid.UUID | None,
    github_handle: str | None,
    kc: float,
    mastery: str,
    certified_via: str | None,
) -> None:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "run_id": run_id,
        "file_path": file_path,
        "module": module,
        "dev_id": dev_id,
        "github_handle": github_handle,
        "kc": kc,
        "mastery": mastery,
        "certified_via": certified_via,
        "computed_at": now,
    }
    update = {
        "module": module,
        "github_handle": github_handle,
        "kc": kc,
        "mastery": mastery,
        "certified_via": certified_via,
        "computed_at": now,
    }
    stmt = pg_insert(FileKc).values(**values)
    if dev_id is not None:
        # Matched dev row → uq_file_kc_dev (dev_id IS NOT NULL).
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "file_path", "dev_id"], index_where=text("dev_id IS NOT NULL"), set_=update
        )
    elif github_handle is not None:
        # Unmatched author (handle only) → uq_file_kc_handle.
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "file_path", "github_handle"],
            index_where=text("dev_id IS NULL AND github_handle IS NOT NULL"),
            set_=update,
        )
    else:
        # Aggregate row → uq_file_kc_agg.
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "file_path"],
            index_where=text("dev_id IS NULL AND github_handle IS NULL"),
            set_=update,
        )
    await session.execute(stmt)


async def _upsert_dependency(session: AsyncSession, *, run_id: uuid.UUID, from_path: str, to_path: str) -> None:
    stmt = pg_insert(Dependency).values(
        id=uuid.uuid4(), run_id=run_id, from_path=from_path, to_path=to_path, computed_at=datetime.now(UTC)
    )
    stmt = stmt.on_conflict_do_nothing(constraint="uq_dependencies_run_from_to")
    await session.execute(stmt)


async def process(request: KcAnalysisRequest, ctx: PipelineContext) -> KcAnalysisResult:
    """Compute KC(file,dev) / KC(file) and wormholes, upserting file_kc / dependencies."""
    if ctx.session is None:
        raise RuntimeError("kc_analysis pipeline requires a DB session in the pipeline context")
    session = ctx.session
    trace: list[str] = []

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        source_paths = _select_source_paths(
            [t.path for t in tree if t.type == "blob" and _is_source(t.path)], _MAX_FILES
        )
        files: dict[str, str] = {}
        blames: dict[str, list[BlameRange]] = {}
        for path in source_paths:
            fc = await client.get_file_content(request.owner, request.repo, path, request.branch)
            if fc.content is not None:
                files[path] = fc.content
            blames[path] = await client.get_blame(request.owner, request.repo, path, request.branch)
        commits = await client.list_commits(request.owner, request.repo, sha=request.branch, per_page=1)
        commit_sha = commits[0].sha if commits else ""
    finally:
        if shared_client is None:
            await client.aclose()
    trace.append(f"fetched {len(source_paths)} source files")

    # Intra-repo dependency edges (wormholes).
    repo_paths = set(files)
    edges = []
    seen_edges: set[tuple[str, str]] = set()
    for path, content in files.items():
        for edge in extract_dependencies(path, content, repo_paths):
            key = (edge.from_path, edge.to_path)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append(edge)

    project_id = uuid.UUID(request.project_id)
    job_id = uuid.UUID(request.job_id)
    run = await _get_or_create_run(
        session, job_id=job_id, project_id=project_id, commit_sha=commit_sha, branch=request.branch
    )

    file_kc_count = 0
    for path in source_paths:
        module = _module_of(path)
        dev_ratios = aggregate_blame(blames.get(path, []))
        dev_kcs: list[float] = []
        for identity, ratio in dev_ratios:
            dev_id = await resolve_author_user_id(session, identity)
            # Cap authorship KC below the dim_star threshold → black_hole (未理解): writing a file is
            # contact, not verified mastery; understanding is raised by quizzes, not blame (issue-048 revisited).
            kc_auth = min(ratio, _AUTHORSHIP_KC_CEILING)
            await _upsert_file_kc(
                session,
                run_id=run.id,
                file_path=path,
                module=module,
                dev_id=dev_id,
                github_handle=identity.login,
                kc=kc_auth,
                mastery=mastery_from_kc(kc_auth, has_contact=True),
                certified_via="authorship",
            )
            dev_kcs.append(kc_auth)
            file_kc_count += 1

        has_contact = len(dev_ratios) > 0
        agg_kc = max(dev_kcs) if dev_kcs else 0.0
        await _upsert_file_kc(
            session,
            run_id=run.id,
            file_path=path,
            module=module,
            dev_id=None,
            github_handle=None,
            kc=agg_kc,
            mastery=mastery_from_kc(agg_kc, has_contact=has_contact),
            certified_via=None,
        )
        file_kc_count += 1

    for edge in edges:
        await _upsert_dependency(session, run_id=run.id, from_path=edge.from_path, to_path=edge.to_path)

    # Drop this run's file_kc / dependency rows for files/edges no longer present (issue-042).
    current_files = set(source_paths)
    stale_kc = delete(FileKc).where(col(FileKc.run_id) == run.id)
    if current_files:
        stale_kc = stale_kc.where(col(FileKc.file_path).notin_(current_files))
    await session.execute(stale_kc)
    stale_dep = delete(Dependency).where(col(Dependency.run_id) == run.id)
    if seen_edges:
        stale_dep = stale_dep.where(tuple_(col(Dependency.from_path), col(Dependency.to_path)).notin_(seen_edges))
    await session.execute(stale_dep)

    run.status = JobStatus.COMPLETED
    session.add(run)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)
    trace.append(f"upserted {file_kc_count} file_kc rows, {len(edges)} dependencies")

    logger.info(
        "kc_analysis: %s file_kc, %s deps for %s/%s@%s",
        file_kc_count,
        len(edges),
        request.owner,
        request.repo,
        commit_sha,
    )
    return KcAnalysisResult(
        job_id=request.job_id,
        job_type=JobType.KC_ANALYSIS,
        status=ResultStatus.COMPLETED,
        project_id=request.project_id,
        run_id=str(run.id),
        commit_sha=commit_sha,
        file_kc_count=file_kc_count,
        dependency_count=len(edges),
        trace=trace,
    )
