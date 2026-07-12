"""kc-analysis pipeline (issue 029) — compute Knowledge Coverage from git authorship/blame.

Fetches a repository snapshot via ``GitHubGitClient`` (method B token), derives KC(file,dev) from
blame line-share (027 authorship matching → ``users.id``), aggregates KC(file), applies the mastery
thresholds, extracts intra-repo dependency edges (wormholes), and upserts ``file_kc`` / ``dependencies``
under an ``analysis_run``. ``shared.worker.run_task`` owns the Job lifecycle + ``result_data``.

KC formula (MVP, ``certified_via="authorship"``): KC(file,dev) = blame line-share × a **size-based initial
estimate** ``_initial_kc_factor`` (``[_KC_INITIAL_FLOOR, _KC_INITIAL_MAX]``). Trivial / boilerplate files
(``__init__.py`` 等・極小行数) start high (理解済み, star 域まで可 — 0.35 超もあり得る); large / complex files
start low (理解負債ホットスポット, black_hole). This disperses initial KC across the matrix for single-author
repos (raw line-share ≈ 1.0 everywhere) instead of a flat value. Understanding is still meant to be
**measured by quizzes** — quiz-certified KC (034, ``certified_via`` != authorship) overwrites these rows.
half-life / decay are unknown (no spec in repo) and intentionally omitted. KC(file) aggregate = max of dev
KCs. See ADR ``docs/adr/0003-kc-mastery-thresholds.md``.

Idempotent across at-least-once redelivery: the run is keyed by ``job_id`` and rows upsert on their
unique constraints (dev rows on ``(run_id, file_path, dev_id)``; aggregate rows on the partial index
``(run_id, file_path) WHERE dev_id IS NULL``).
"""

import logging
import math
import posixpath
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.pipelines.run_cleanup import prune_superseded_runs
from service.services import code_analysis
from service.services.authorship import AuthorIdentity, resolve_author_user_id
from service.services.dependency_extraction import extract_dependencies
from service.services.github_app import GitHubAppService
from service.services.github_git_client import BlameRange, GitHubGitClient
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, Dependency, FileKc
from shared.pipelines.context import PipelineContext
from shared.schemas.kc_analysis import KcAnalysisRequest, KcAnalysisResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

# 初期 KC（authorship）を「規模＝理解負荷」で分散させる推定モデル。単独著者リポジトリだと blame 行シェアが
# 全ファイル≒1.0 になり KC が一律になってしまうため、行数（対数スケール）で 0..1 に写像し、KC レンジ
# ``[_KC_INITIAL_FLOOR, _KC_INITIAL_MAX]`` に配分する:
#  - 極小コード / ボイラープレート（``__init__.py`` 等）は初めから高い＝理解済み（star 域, 0.35 超もあり得る）
#  - 大きい/複雑なファイルほど低い＝理解負債ホットスポット（black_hole）
# 旧仕様の一律 0.35 上限は撤廃。クイズ実測 KC（certified_via != authorship）はこの推定の対象外で、実測が
# 入ればそれで上書きされる（理解はクイズで実測、という product 前提は維持）。
_KC_SIZE_MIN_LINES = 6  # これ以下は最大（極小＝理解しやすい）
_KC_SIZE_MAX_LINES = 500  # これ以上は floor（大きい＝理解負荷大）
_KC_INITIAL_MAX = 0.9  # 極小/ボイラープレートの初期 KC（star 域）
_KC_INITIAL_FLOOR = 0.05  # 巨大ファイルの初期 KC（未理解）
# 中身がほぼ定型で、書いた時点で理解済みとみなせるボイラープレート（サイズに依らず高 KC）。
_BOILERPLATE_NAMES = frozenset({"__init__.py", "__main__.py", "py.typed"})


def _initial_kc_factor(path: str, content: str) -> float:
    """Return the initial authorship-KC estimate in ``[_KC_INITIAL_FLOOR, _KC_INITIAL_MAX]``.

    Trivial / boilerplate files start high (understood); larger files start low (knowledge-debt
    hotspots). Log scale spreads typical code (tens–hundreds of lines) across the whole range.
    """
    if path.rsplit("/", 1)[-1] in _BOILERPLATE_NAMES:
        return _KC_INITIAL_MAX
    lines = content.count("\n") + 1 if content else 0
    if lines <= _KC_SIZE_MIN_LINES:
        shape = 1.0
    else:
        span = math.log(_KC_SIZE_MAX_LINES) - math.log(_KC_SIZE_MIN_LINES)
        shape = max(0.0, min(1.0, 1.0 - (math.log(lines) - math.log(_KC_SIZE_MIN_LINES)) / span))
    return _KC_INITIAL_FLOOR + (_KC_INITIAL_MAX - _KC_INITIAL_FLOOR) * shape


async def _mint_installation_token(github: GitHubRef) -> str:
    """Method B: explicit access_token if present, else mint from the Secret Manager key."""
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


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
    preserve_measured: bool = False,
) -> None:
    # preserve_measured: 再 blame の authorship 書き込みが、持ち越したクイズ/レビュー実測行を上書きしないよう
    # ON CONFLICT DO UPDATE に「実測でない行のみ更新」ガードを付ける（差分再解析での KC 保全）。
    measured_guard = (
        text("file_kc.certified_via IS DISTINCT FROM 'quiz' AND file_kc.certified_via IS DISTINCT FROM 'review'")
        if preserve_measured
        else None
    )
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
            index_elements=["run_id", "file_path", "dev_id"],
            index_where=text("dev_id IS NOT NULL"),
            set_=update,
            where=measured_guard,
        )
    elif github_handle is not None:
        # Unmatched author (handle only) → uq_file_kc_handle.
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "file_path", "github_handle"],
            index_where=text("dev_id IS NULL AND github_handle IS NOT NULL"),
            set_=update,
            where=measured_guard,
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


async def _prior_completed_kc_run(session: AsyncSession, project_id: uuid.UUID) -> AnalysisRun | None:
    """Return the project's latest COMPLETED kc_analysis run (the carry-forward source).

    The new run is PROCESSING at call time, so it is naturally excluded — same axis readers and quiz
    grading use.
    """
    return (
        (
            await session.execute(
                select(AnalysisRun)
                .where(
                    col(AnalysisRun.project_id) == project_id,
                    col(AnalysisRun.kind) == JobType.KC_ANALYSIS.value,
                    col(AnalysisRun.status) == JobStatus.COMPLETED,
                )
                .order_by(col(AnalysisRun.created_at).desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _carry_forward_kc(
    session: AsyncSession, *, prior_run_id: uuid.UUID, new_run_id: uuid.UUID, kept: set[str], to_reblame: set[str]
) -> int:
    """Copy the prior run's file_kc rows into the new run so re-analysis never resets KC.

    Unchanged files (in ``kept`` but not ``to_reblame``): copy every row (authorship + measured + aggregate).
    Changed/new files (in ``to_reblame``): copy ONLY measured rows (``certified_via`` in quiz/review) — their
    authorship + aggregate are recomputed from fresh blame. Files no longer selected (not in ``kept``) drop.
    """
    rows = (await session.execute(select(FileKc).where(col(FileKc.run_id) == prior_run_id))).scalars().all()
    copied = 0
    for r in rows:
        if r.file_path not in kept:
            continue
        if r.file_path in to_reblame and r.certified_via not in ("quiz", "review"):
            continue
        session.add(
            FileKc(
                id=uuid.uuid4(),
                run_id=new_run_id,
                file_path=r.file_path,
                module=r.module,
                dev_id=r.dev_id,
                github_handle=r.github_handle,
                kc=r.kc,
                mastery=r.mastery,
                certified_via=r.certified_via,
                computed_at=r.computed_at,
            )
        )
        copied += 1
    return copied


async def _recompute_aggregate(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    file_path: str,
    module: str,
    extra_kc: float = 0.0,
    has_authors: bool = False,
) -> None:
    """Re-derive the aggregate KC row (dev_id/handle NULL) as max over the file's per-dev rows.

    Includes carried-forward quiz-measured rows. ``extra_kc`` folds in authorship contributions that
    have no per-dev row (login-less authors — dev_id/handle both NULL — collide with the aggregate
    slot); ``has_authors`` marks that the file had blame contact (so it isn't shown as "unexplored").
    Mirrors quiz_grading._reflect_quiz_kc.
    """
    rows = (
        (
            await session.execute(
                select(FileKc).where(
                    col(FileKc.run_id) == run_id,
                    col(FileKc.file_path) == file_path,
                    ~(col(FileKc.dev_id).is_(None) & col(FileKc.github_handle).is_(None)),
                )
            )
        )
        .scalars()
        .all()
    )
    has_contact = len(rows) > 0 or has_authors
    agg_kc = max((r.kc for r in rows), default=0.0)
    agg_kc = max(agg_kc, extra_kc)
    await _upsert_file_kc(
        session,
        run_id=run_id,
        file_path=file_path,
        module=module,
        dev_id=None,
        github_handle=None,
        kc=agg_kc,
        mastery=mastery_from_kc(agg_kc, has_contact=has_contact),
        certified_via=None,
    )


async def process(
    request: KcAnalysisRequest,
    ctx: PipelineContext,
    *,
    changed_paths: set[str] | None = None,
    head_sha: str | None = None,
) -> KcAnalysisResult:
    """Compute KC(file,dev) / KC(file) and wormholes, upserting file_kc / dependencies.

    Incremental re-analysis (Phase 1): ``changed_paths`` (None = full) scopes the expensive per-file
    blame to changed/new files; unchanged files' KC — including quiz-measured values — is carried
    forward from the prior COMPLETED run so re-analysis never resets understanding.
    """
    if ctx.session is None:
        raise RuntimeError("kc_analysis pipeline requires a DB session in the pipeline context")
    session = ctx.session
    trace: list[str] = []

    project_id = uuid.UUID(request.project_id)
    job_id = uuid.UUID(request.job_id)

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        # kc_analysis と feature_clustering は同じ選定（code_analysis.select_source_paths + 同一上限）を使い、
        # 同一ファイル集合を採点する（galaxy が別母集合を union して機能ファイルが未着手表示になるのを防ぐ）。
        source_paths = code_analysis.select_source_paths(
            [t.path for t in tree if t.type == "blob"], config.analysis_max_files()
        )
        # 差分再解析（Phase 1）: 前 COMPLETED KC run と、その採点済みファイル集合を引く。changed_paths が
        # 与えられていれば「変更ファイル＋前 run に無い新規ファイル」だけを再 blame し、未変更ファイルは
        # 前 run の file_kc をそのまま持ち越す。prior 無し / changed_paths=None はフル再 blame（それでも
        # クイズ実測行は持ち越して保全する）。
        prior_run = await _prior_completed_kc_run(session, project_id)
        prior_files: set[str] = set()
        if prior_run is not None:
            prior_files = set(
                (
                    await session.execute(
                        select(col(FileKc.file_path)).where(col(FileKc.run_id) == prior_run.id).distinct()
                    )
                )
                .scalars()
                .all()
            )
        if changed_paths is None or prior_run is None:
            to_reblame = set(source_paths)
        else:
            to_reblame = {p for p in source_paths if p in changed_paths or p not in prior_files}

        files: dict[str, str] = {}
        blames: dict[str, list[BlameRange]] = {}
        for path in source_paths:
            # Content は全ファイル取得（依存抽出のため。clone があればローカル読み取りで安価）。
            fc = await client.get_file_content(request.owner, request.repo, path, request.branch)
            if fc.content is not None:
                files[path] = fc.content
            # Blame（高価な per-file GraphQL）は再解析対象だけに絞る。未変更は前 run から持ち越す。
            if path in to_reblame:
                blames[path] = await client.get_blame(request.owner, request.repo, path, request.branch)
        if head_sha:
            commit_sha = head_sha  # orchestrator が diff した HEAD をそのまま記録（次回 diff の基点を一貫させる）。
        else:
            commits = await client.list_commits(request.owner, request.repo, sha=request.branch, per_page=1)
            commit_sha = commits[0].sha if commits else ""
    finally:
        if shared_client is None:
            await client.aclose()
    incremental = prior_run is not None
    trace.append(f"fetched {len(source_paths)} files; re-blamed {len(to_reblame)} (incremental={incremental})")

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

    run = await _get_or_create_run(
        session, job_id=job_id, project_id=project_id, commit_sha=commit_sha, branch=request.branch
    )

    # 差分再解析: 未変更ファイル（＋常にクイズ/レビュー実測行）を前 run から新 run へ持ち越す。以降の再 blame
    # upsert が持ち越し行を参照できるよう flush する（authorship は preserve_measured ガードで実測を壊さない）。
    carried = 0
    if prior_run is not None:
        carried = await _carry_forward_kc(
            session, prior_run_id=prior_run.id, new_run_id=run.id, kept=set(source_paths), to_reblame=to_reblame
        )
        await session.flush()

    file_kc_count = carried
    for path in sorted(to_reblame):
        module = _module_of(path)
        dev_ratios = aggregate_blame(blames.get(path, []))
        # 規模ベースの初期KC推定（極小/ボイラープレート=高い＝理解済み / 大=低い＝理解負債）。行シェアが
        # 一律でも spread が出る。旧仕様の 0.35 上限は撤廃（トリビアルなファイルは star 域まで上がる）。
        # 内容を取得できなかったファイル（大きすぎ/バイナリ/取得失敗＝`files` に不在）は、行数 0 → 極小扱いで
        # 高 KC（理解済み）に誤反転させず floor（未理解ホットスポット）に倒す。空ファイル("")は `files` に有る。
        init_kc = _initial_kc_factor(path, files[path]) if path in files else _KC_INITIAL_FLOOR
        extra_kc = 0.0  # login-less 著者（per-dev 行を書けない）の authorship 寄与を集約に畳み込む。
        for identity, ratio in dev_ratios:
            dev_id = await resolve_author_user_id(session, identity)
            kc_auth = min(ratio, 1.0) * init_kc
            handle = identity.login or None  # 空文字も None 扱い（handle 分岐の空ハンドル書き込みを避ける）。
            if dev_id is None and handle is None:
                # dev_id も handle も無い著者は per-dev 行として一意に表現できず、書くと集約行スロット
                # （uq_file_kc_agg: dev_id IS NULL AND github_handle IS NULL）と衝突・相互上書きする。
                # 集約 KC には extra_kc として反映（per-dev 行は書かない）。
                extra_kc = max(extra_kc, kc_auth)
                continue
            await _upsert_file_kc(
                session,
                run_id=run.id,
                file_path=path,
                module=module,
                dev_id=dev_id,
                github_handle=handle,
                kc=kc_auth,
                mastery=mastery_from_kc(kc_auth, has_contact=True),
                certified_via="authorship",
                preserve_measured=True,  # 持ち越したクイズ実測（同一 file×dev）を authorship で潰さない。
            )
            file_kc_count += 1

        # 集約行は DB の全 per-dev 行（再 blame authorship ＋ 持ち越しクイズ実測）＋ login-less 寄与から再計算。
        await _recompute_aggregate(
            session,
            run_id=run.id,
            file_path=path,
            module=module,
            extra_kc=extra_kc,
            has_authors=len(dev_ratios) > 0,
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
    # 再解析で古い run のファイル行が溜まり「同一ファイルが複数登録」になるのを防ぐ（最新 run のみ残す）。
    await prune_superseded_runs(session, project_id=run.project_id, kind=JobType.KC_ANALYSIS.value, keep_run_id=run.id)
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
