"""feature-clustering pipeline (issue 052).

Groups a repository's source files into product *features* via Gemini (Vertex AI + ADC), using
the file list + intra-repo import graph as the main signal. Results are persisted to ``features``
/ ``feature_files`` under an ``analysis_run`` (snapshot axis). ``shared.worker.run_task`` owns the
``Job`` lifecycle + ``result_data`` and the single terminal commit (issue-042).

Idempotent across Cloud Tasks at-least-once redelivery: the ``analysis_run`` is keyed by
``job_id`` (reused on retry) and ``features`` upsert on ``(run_id, key)`` / ``feature_files`` on
``(run_id, feature_id, file_path)`` — so the (non-deterministic) feature set does not duplicate.
"""

import logging
import posixpath
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.pipelines.run_cleanup import prune_superseded_runs
from service.services import code_analysis, feature_authoring, feature_communities, gemini_stack_service
from service.services.dependency_extraction import extract_dependencies
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.analysis_scope import is_learnable_path
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, Feature, FeatureFile, LearningPlan, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.feature_clustering import FeatureClusteringRequest, FeatureClusteringResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_PROPAGATED_CONFIDENCE = 0.5  # confidence for files added by graph-community propagation (vs LLM-asserted)
# グラフ伝播で 1 機能に追加できるファイル数の上限。密結合リポジトリでは import グラフが 1 塊になり、
# ラベル伝播が backend 全体を（seed を持つ）1 機能へ流し込む（実測: 学習に 58 ファイル流入）。上限を設けて
# その暴走を抑える。本来の割当は LLM（各ファイルの用途つき）に任せ、グラフは軽い補強に留める。
_MAX_GRAPH_ADD = 6
_BACKFILL_CONFIDENCE = 0.3  # confidence for files added by directory backfill (weakest signal)
_MIN_FEATURE_FILES = 3  # 各機能に最低これだけ実ファイルを割り当てる（"複数" を保証。近傍で best-effort 補完）
_INCREMENTAL_CONFIDENCE = 0.8  # 増分再解析で既存機能へ割り当て直したファイルの confidence（LLM 割当）
# フル再クラスタで新クラスタが前 run のどの機能と「同一」かを判定する閾値（小さい方の集合に対する重なり率）。
# これ以上重なれば前 run の key を再利用し、feature_key を安定させる（クイズ/学習を維持）。
_KEY_REUSE_CONTAINMENT = 0.5


def _norm(s: object) -> str:
    """Collapse case/punctuation so an LLM-returned capability id resolves to a canonical feature key."""
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _dir_of(path: str) -> str:
    """The directory portion of a repo-relative path ("" for repo-root files)."""
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _path_resolver(source_paths: list[str]) -> Callable[[str], str | None]:
    """Build a resolver mapping an LLM-returned path to a canonical tree path (issue 074-C style).

    Exact-set membership dropped every near-miss (``./`` prefix, separators, repo- vs feature-relative,
    the 200-file cap boundary). Normalize via ``posixpath.normpath`` first, then fall back to a *uniquely*
    matching basename so the real files a feature was built from are recovered instead of silently lost
    (which is what left features with zero displayable files). Returns ``None`` when unresolvable.
    """
    norm_to_canon = {posixpath.normpath(p): p for p in source_paths}
    base_to_canon: dict[str, list[str]] = {}
    for p in source_paths:
        base_to_canon.setdefault(p.rsplit("/", 1)[-1], []).append(p)

    def resolve(candidate: str) -> str | None:
        if not candidate:
            return None
        canon = norm_to_canon.get(posixpath.normpath(candidate))
        if canon is not None:
            return canon
        cands = base_to_canon.get(candidate.rsplit("/", 1)[-1], [])
        return cands[0] if len(cands) == 1 else None

    return resolve


def _canonical_members(cluster: dict, resolve: Callable[[str], str | None]) -> dict[str, float]:
    """Resolve a cluster's LLM file entries to canonical repo paths → ``{path: best confidence}``."""
    files_val = cluster.get("files")
    members = files_val if isinstance(files_val, list) else []
    resolved: dict[str, float] = {}
    for f in members:
        if not isinstance(f, dict):
            continue
        canon = resolve(str(f.get("path") or ""))
        if canon is None:
            continue
        try:
            conf = float(f.get("confidence", 1.0))
        except (TypeError, ValueError):
            conf = 1.0
        if canon not in resolved or conf > resolved[canon]:
            resolved[canon] = conf
    return resolved


def _backfill_features(clusters: list, source_paths: list[str]) -> None:
    """Top each feature up to ``_MIN_FEATURE_FILES`` using UNASSIGNED same-directory files (in place).

    Only files no feature already claims are used (consumed from a shared pool), so backfill never steals
    another feature's file or cross-contaminates two features that share a directory. Features already at
    the minimum, and files with no unassigned neighbours, are left as-is (best-effort — we never fabricate
    paths that don't exist in the tree). A feature with zero real files is left empty here and dropped at
    persistence (a spurious feature the model invented over non-existent paths).
    """
    assigned: set[str] = set()
    for c in clusters:
        if isinstance(c, dict):
            for f in c.get("files") or []:
                if isinstance(f, dict) and f.get("path"):
                    assigned.add(str(f["path"]))
    pool_by_dir: dict[str, list[str]] = {}
    for p in source_paths:
        if p not in assigned:
            pool_by_dir.setdefault(_dir_of(p), []).append(p)

    for c in clusters:
        if not isinstance(c, dict):
            continue
        members = list(c["files"]) if isinstance(c.get("files"), list) else []
        existing = {str(f.get("path")) for f in members if isinstance(f, dict) and f.get("path")}
        if not existing or len(existing) >= _MIN_FEATURE_FILES:
            continue
        for d in sorted({_dir_of(p) for p in existing}):
            pool = pool_by_dir.get(d, [])
            while pool and len(existing) < _MIN_FEATURE_FILES:
                p = pool.pop(0)  # consume so no other feature reuses it
                existing.add(p)
                members.append({"path": p, "confidence": _BACKFILL_CONFIDENCE})
            if len(existing) >= _MIN_FEATURE_FILES:
                break
        c["files"] = members


async def _mint_installation_token(github: GitHubRef) -> str:
    """Method B: use an explicit access_token if present, else mint from the Secret Manager key."""
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def _get_or_create_run(
    session: AsyncSession, *, job_id: uuid.UUID, project_id: uuid.UUID, commit_sha: str, branch: str
) -> AnalysisRun:
    """Reuse the run for this job (idempotent retry) or create a new PROCESSING run."""
    existing = (
        await session.execute(
            select(AnalysisRun).where(
                col(AnalysisRun.job_id) == job_id,
                col(AnalysisRun.kind) == JobType.FEATURE_CLUSTERING.value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    run = AnalysisRun(
        project_id=project_id,
        commit_sha=commit_sha,
        branch=branch,
        kind=JobType.FEATURE_CLUSTERING.value,
        job_id=job_id,
        status=JobStatus.PROCESSING,
    )
    session.add(run)
    await session.flush()
    return run


async def _upsert_feature(
    session: AsyncSession, *, run_id: uuid.UUID, project_id: uuid.UUID, key: str, name: str, description: str
) -> uuid.UUID:
    """Upsert one feature and return its id (re-read after the flushed upsert)."""
    now = datetime.now(UTC)
    stmt = pg_insert(Feature).values(
        id=uuid.uuid4(),
        project_id=project_id,
        run_id=run_id,
        key=key,
        name=name,
        description=description,
        source="ai",
        computed_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_features_run_key",
        set_={"name": name, "description": description, "source": "ai", "computed_at": now},
    )
    await session.execute(stmt)
    row = (
        await session.execute(select(Feature).where(col(Feature.run_id) == run_id, col(Feature.key) == key))
    ).scalar_one()
    return row.id


async def _upsert_feature_file(
    session: AsyncSession, *, run_id: uuid.UUID, feature_id: uuid.UUID, file_path: str, confidence: float
) -> None:
    stmt = pg_insert(FeatureFile).values(
        id=uuid.uuid4(), run_id=run_id, feature_id=feature_id, file_path=file_path, confidence=confidence
    )
    stmt = stmt.on_conflict_do_update(constraint="uq_feature_files_run_feature_path", set_={"confidence": confidence})
    await session.execute(stmt)


async def _prior_completed_feature_run(session: AsyncSession, project_id: uuid.UUID) -> AnalysisRun | None:
    """The project's latest COMPLETED feature_clustering run (the carry-forward source)."""
    return (
        (
            await session.execute(
                select(AnalysisRun)
                .where(
                    col(AnalysisRun.project_id) == project_id,
                    col(AnalysisRun.kind) == JobType.FEATURE_CLUSTERING.value,
                    col(AnalysisRun.status) == JobStatus.COMPLETED,
                )
                .order_by(col(AnalysisRun.created_at).desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _carry_forward_features(
    session: AsyncSession, *, prior_run_id: uuid.UUID, new_run_id: uuid.UUID, project_id: uuid.UUID
) -> tuple[int, int]:
    """Copy the prior run's features + memberships into the new run, preserving each feature's key.

    ``key`` stays stable (new per-run ``id``) so quizzes/learning resolved by ``feature_key`` stay
    attached across re-analysis instead of orphaning. Returns ``(feature_count, file_count)``.
    """
    prior_features = (await session.execute(select(Feature).where(col(Feature.run_id) == prior_run_id))).scalars().all()
    feature_count = 0
    file_count = 0
    for pf in prior_features:
        new_id = await _upsert_feature(
            session, run_id=new_run_id, project_id=project_id, key=pf.key, name=pf.name, description=pf.description
        )
        feature_count += 1
        ff_rows = (
            (
                await session.execute(
                    select(FeatureFile).where(
                        col(FeatureFile.run_id) == prior_run_id, col(FeatureFile.feature_id) == pf.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for ff in ff_rows:
            await _upsert_feature_file(
                session, run_id=new_run_id, feature_id=new_id, file_path=ff.file_path, confidence=ff.confidence
            )
            file_count += 1
    return feature_count, file_count


async def _feature_memberships(session: AsyncSession, run_id: uuid.UUID) -> dict[str, set[str]]:
    """Return ``{feature_key: {file_path, ...}}`` for a run (Feature ⋈ FeatureFile)."""
    rows = (
        await session.execute(
            select(col(Feature.key), col(FeatureFile.file_path))
            .join(FeatureFile, col(FeatureFile.feature_id) == col(Feature.id))
            .where(col(Feature.run_id) == run_id, col(FeatureFile.run_id) == run_id)
        )
    ).all()
    members: dict[str, set[str]] = {}
    for key, path in rows:
        members.setdefault(key, set()).add(path)
    return members


def _reconcile_keys(clusters: list, prior_members: dict[str, set[str]]) -> int:
    """Reuse a prior feature's key for a new cluster that covers mostly the same files (in place).

    A full re-cluster mints fresh keys, which would orphan/regenerate quizzes/learning (resolved by
    ``feature_key``). Match each new cluster to a prior feature by file overlap (containment vs the
    smaller set) and, greedily 1:1 above ``_KEY_REUSE_CONTAINMENT``, adopt the prior key so dedup and
    the hub keep the existing quiz/plan. Genuinely-new clusters (no overlap) keep their fresh key.
    Returns the number of keys remapped. Expects each cluster's ``files`` to be canonical repo paths.
    """
    if not prior_members:
        return 0
    cluster_files: list[set[str]] = []
    for c in clusters:
        files: set[str] = set()
        if isinstance(c, dict):
            for f in c.get("files") or []:
                if isinstance(f, dict) and f.get("path"):
                    files.add(str(f["path"]))
        cluster_files.append(files)
    scored: list[tuple[float, int, str]] = []
    for ci, files in enumerate(cluster_files):
        if not files:
            continue
        for pkey, pfiles in prior_members.items():
            inter = len(files & pfiles)
            if inter:
                scored.append((inter / min(len(files), len(pfiles)), ci, pkey))
    scored.sort(key=lambda t: t[0], reverse=True)
    used_cluster: set[int] = set()
    used_prior: set[str] = set()
    remapped = 0
    for score, ci, pkey in scored:
        if score < _KEY_REUSE_CONTAINMENT:
            break
        if ci in used_cluster or pkey in used_prior:
            continue
        c = clusters[ci]
        if isinstance(c, dict) and c.get("key") != pkey:
            c["key"] = pkey
            remapped += 1
        used_cluster.add(ci)
        used_prior.add(pkey)
    return remapped


async def _mark_features_stale(session: AsyncSession, *, project_id: uuid.UUID, feature_keys: set[str]) -> None:
    """Flag every quiz/learning-plan of the given feature keys as ``stale`` (files changed → 要再受験).

    A membership change is a property of the feature, so it fans out to all developers' rows for that
    ``feature_key``. Fresh retest sessions default to ``stale=False``, so the flag naturally resets.
    """
    if not feature_keys:
        return
    keys = list(feature_keys)
    await session.execute(
        update(QuizSession)
        .where(col(QuizSession.project_id) == project_id, col(QuizSession.feature_key).in_(keys))
        .values(stale=True)
    )
    await session.execute(
        update(LearningPlan)
        .where(col(LearningPlan.project_id) == project_id, col(LearningPlan.feature_key).in_(keys))
        .values(stale=True)
    )


async def process(
    request: FeatureClusteringRequest,
    ctx: PipelineContext,
    *,
    clusters: list[dict] | None = None,
    graph_edges: list[tuple[str, str]] | None = None,
    changed_paths: set[str] | None = None,
    removed_paths: set[str] | None = None,
    head_sha: str | None = None,
) -> FeatureClusteringResult:
    """Cluster the repository's source files into features and upsert them under an analysis run.

    ``clusters`` (issue 268, agent-first): when provided (non-None) — e.g. the Base Analysis Agent's
    ``BaseAnalysis.features`` — those clusters are used directly and the feature-clustering model call
    is skipped (this pipeline just formats/persists the agent output). When ``None`` (standalone run,
    or an empty base) the existing agentic clustering runs (``cluster_features_agentic`` → direct
    Gemini fallback). Either way the tree is fetched so only real repo paths are accepted.

    ``graph_edges`` (issue 293, 方針A): the repository's file↔file call graph (CGC ``file_edges``),
    supplied by the agentic orchestrator. When present it re-aligns feature memberships to graph
    communities (seeded label propagation) so each feature covers a connected, hub-centered region of
    related code. When ``None`` (standalone run) the locally-built import graph is used instead.

    ``changed_paths`` / ``removed_paths`` (Phase 2a incremental): when a prior feature run exists, the
    diff is small (churn ≤ ``config.feature_recluster_churn_threshold()``), and ``changed_paths`` is not
    None, the feature set is carried forward (stable keys) and ONLY changed/new files are re-assigned to
    existing features while removed files are dropped — cheap, and quizzes/learning stay attached. A
    feature whose file set changes has its quizzes/plans flagged ``stale`` (要再受験). Otherwise (first
    run / manual full / high churn) a FULL re-cluster runs — the only path that mints new features/keys.
    """
    if ctx.session is None:
        raise RuntimeError("feature_clustering pipeline requires a DB session in the pipeline context")
    session = ctx.session
    trace: list[str] = []
    from_base = clusters is not None

    # 差分再解析（Phase 2a）: 前 feature run があり diff が使え churn が閾値内なら「増分」— 新規/変更ファイルだけを
    # 既存機能（key 固定）へ割当し直し、他は持ち越す（クイズ/学習は feature_key で紐付いたまま）。前 run 無し /
    # 手動フル(changed_paths=None) / churn 超過は「フル再クラスタ」（新 key/新機能が生まれる唯一の経路）。
    project_id = uuid.UUID(request.project_id)
    job_id = uuid.UUID(request.job_id)
    prior_feature_run = await _prior_completed_feature_run(session, project_id)
    prior_members: dict[str, set[str]] = {}
    prior_files: set[str] = set()
    if prior_feature_run is not None:
        prior_members = await _feature_memberships(session, prior_feature_run.id)
        for paths in prior_members.values():
            prior_files |= paths
    churn = len(changed_paths or set()) + len(removed_paths or set())
    do_incremental = (
        prior_feature_run is not None
        and changed_paths is not None
        and bool(prior_files)
        and churn <= config.feature_recluster_churn_threshold() * len(prior_files)
    )

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    source_paths: list[str] = []
    files: dict[str, str] = {}
    affected: list[str] = []
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        # kc_analysis と同じ選定（round-robin・.svelte/.vue 含む・同一上限）で同一ファイル集合を対象にする。
        source_paths = code_analysis.select_source_paths(
            [t.path for t in tree if t.type == "blob"], config.analysis_max_files()
        )
        if do_incremental:
            # 影響ファイル: 学習対象のうち「変更された or 前 run の機能に無い（新規）」もの。content は descriptors 用。
            affected = [
                p for p in source_paths if is_learnable_path(p) and (p in changed_paths or p not in prior_files)
            ]
            for path in affected:
                fc = await client.get_file_content(request.owner, request.repo, path, request.branch)
                if fc.content is not None:
                    files[path] = fc.content
        elif not from_base:
            # フル（非 base）: import グラフ用に全 content を取得。
            for path in source_paths:
                fc = await client.get_file_content(request.owner, request.repo, path, request.branch)
                if fc.content is not None:
                    files[path] = fc.content
        if head_sha:
            commit_sha = head_sha
        else:
            commits = await client.list_commits(request.owner, request.repo, sha=request.branch, per_page=1)
            commit_sha = commits[0].sha if commits else ""
    finally:
        if shared_client is None:
            await client.aclose()
    trace.append(
        f"incremental: {len(affected)} affected of {len(source_paths)} files"
        if do_incremental
        else f"fetched {len(source_paths)} files"
    )

    # Intra-repo import graph (main clustering signal) — only when we run the full clustering model.
    edges: list[tuple[str, str]] = []
    if not from_base and not do_incremental:
        repo_paths = set(files)
        seen: set[tuple[str, str]] = set()
        for path, content in files.items():
            for edge in extract_dependencies(path, content, repo_paths):
                key = (edge.from_path, edge.to_path)
                if key not in seen:
                    seen.add(key)
                    edges.append(key)

    run = await _get_or_create_run(
        session, job_id=job_id, project_id=project_id, commit_sha=commit_sha, branch=request.branch
    )

    if do_incremental:
        # 前 run の機能セット（key 固定）を新 run へ複製 → 変更/新規ファイルだけ既存機能へ割当し直す。
        feature_count, _ = await _carry_forward_features(
            session, prior_run_id=prior_feature_run.id, new_run_id=run.id, project_id=project_id
        )
        # 影響ファイル＋削除/選外ファイルの既存 membership を落とす（この後で影響ファイルを貼り直す）。
        gone = set(removed_paths or set()) | (prior_files - set(source_paths))
        drop = set(affected) | gone
        if drop:
            await session.execute(
                delete(FeatureFile).where(col(FeatureFile.run_id) == run.id, col(FeatureFile.file_path).in_(list(drop)))
            )
        # 新 run の機能（key/name/description）を固定 capability として、影響ファイルを割り当て直す（多重可）。
        new_features = (await session.execute(select(Feature).where(col(Feature.run_id) == run.id))).scalars().all()
        key_to_id = {f.key: f.id for f in new_features}
        resolve: dict[str, str] = {}
        for f in new_features:
            resolve[_norm(f.key)] = f.key
            resolve[_norm(f.name)] = f.key
        assignments: dict[str, list[str]] = {}
        if affected and new_features:
            caps = [{"key": f.key, "name": f.name, "description": f.description} for f in new_features]
            fwp = [(p, code_analysis.file_purpose(files.get(p, ""))) for p in affected]
            assignments = await gemini_stack_service.assign_files_to_capabilities(caps, fwp)
        for path in affected:
            raw = assignments.get(path) or []
            canon: list[str] = []
            for k in raw if isinstance(raw, list) else [raw]:
                ck = resolve.get(_norm(k))
                if ck and ck not in canon:
                    canon.append(ck)
            for ck in canon:
                await _upsert_feature_file(
                    session, run_id=run.id, feature_id=key_to_id[ck], file_path=path, confidence=_INCREMENTAL_CONFIDENCE
                )
        # stale 検知: 前 run と membership が変わった機能のクイズ/学習を「要再受験」にする（返済ループ駆動）。
        new_members = await _feature_memberships(session, run.id)
        changed_keys = {
            k
            for k in (set(prior_members) | set(new_members))
            if prior_members.get(k, set()) != new_members.get(k, set())
        }
        await _mark_features_stale(session, project_id=project_id, feature_keys=changed_keys)
        file_count = sum(len(v) for v in new_members.values())
        trace.append(f"incremental: reassigned {len(affected)} files, {len(changed_keys)} features marked stale")
        run.status = JobStatus.COMPLETED
        session.add(run)
        await session.flush()
        await prune_superseded_runs(
            session, project_id=run.project_id, kind=JobType.FEATURE_CLUSTERING.value, keep_run_id=run.id
        )
        logger.info(
            "feature_clustering: incremental — %s features / %s memberships, %s stale for %s/%s@%s",
            feature_count,
            file_count,
            len(changed_keys),
            request.owner,
            request.repo,
            commit_sha,
        )
        return FeatureClusteringResult(
            job_id=request.job_id,
            job_type=JobType.FEATURE_CLUSTERING,
            status=ResultStatus.COMPLETED,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            feature_count=feature_count,
            file_count=file_count,
            trace=trace,
        )

    if from_base:
        # Format/persist the Base Analysis Agent's features (no model call).
        trace.append(f"using {len(clusters)} features from base analysis")
    else:
        # capability-first クラスタリング: LLM が能力名を列挙 → ファイルをバッチで固定能力へ割当（多重可）。
        # 単発クラスタリングが 400 ファイルを割り当てきれずカバレッジ 6% になる問題への対策。各ファイルの用途
        # （module docstring / 先頭コメント）を添えて渡し「何をするコードか」で割り当てさせる。ボイラープレート
        # （__init__.py / __main__.py）は学習/機能の対象外なので候補から除外する。
        descriptors = {p: d for p, d in ((p, code_analysis.file_purpose(c)) for p, c in files.items()) if d}
        cluster_paths = [p for p in source_paths if is_learnable_path(p)]
        clusters = await feature_authoring.cluster_features_capability_first(
            cluster_paths, edges, owner=request.owner, repo=request.repo, descriptors=descriptors
        )
    valid_paths = set(source_paths)

    # 取りこぼし回収（issue: 機能に実ファイルが割り当たらず理解度マップが空になる）: LLM の返す path を
    # 完全一致で捨てず、正規化/一意 basename で tree の実 path に解決してから canonical 化する。以降のグラフ
    # 拡張・補完・永続化はこの正規化済み members を前提にする。
    resolve = _path_resolver(source_paths)
    for c in clusters:
        if isinstance(c, dict):
            resolved = _canonical_members(c, resolve)
            c["files"] = [{"path": p, "confidence": conf} for p, conf in resolved.items()]

    # フル再クラスタでも、前 run と大部分のファイルが重なる機能は前 run の key を再利用して feature_key を
    # 安定させる（→ クイズ/学習が dedup で維持され、全再生成/orphan にならない）。LLM 割当の canonical members
    # を使い、グラフ拡張/バックフィルでノイズが乗る前に判定する。
    reused = _reconcile_keys(clusters, prior_members)
    if reused:
        trace.append(f"reused {reused} prior feature keys (key stabilization on full re-cluster)")

    # Graph-community re-alignment (issue 293, 方針A): grow each feature along the repo call graph so
    # memberships match hub-centered communities and each feature covers a connected region of related
    # code (fixes "the filter leaves only 1–2 files"). Uses the CGC file_edges passed by the agentic
    # orchestrator (from_base), else the locally-built import graph (standalone). LLM labels/names are
    # kept; propagated files are added at a lower confidence.
    # グラフコミュニティ再整列は **base-agent が疎な機能を返したとき（from_base）だけ** 効かせる。
    # capability-first 経路（from_base=False）は LLM がバッチ割当で全ファイルをカバー済みで、伝播は無関係
    # ファイルを引き込むノイズにしかならないためスキップする（CGC 空時はローカル import グラフにフォールバック）。
    effective_edges = graph_edges or edges
    if from_base and effective_edges:
        seeds: dict[str, set[str]] = {}
        for c in clusters:
            if not isinstance(c, dict):
                continue
            key = str(c.get("key") or "").strip()
            if not key:
                continue
            files_val = c.get("files")
            members = files_val if isinstance(files_val, list) else []
            paths = {str(f.get("path") or "") for f in members if isinstance(f, dict)}
            seeds.setdefault(key, set()).update(p for p in paths if p in valid_paths)
        communities = feature_communities.assign_communities(seeds, effective_edges, valid_paths)
        for c in clusters:
            if not isinstance(c, dict):
                continue
            key = str(c.get("key") or "").strip()
            if not key:
                continue
            files_val = c.get("files")
            members = list(files_val) if isinstance(files_val, list) else []
            existing = {str(f.get("path") or "") for f in members if isinstance(f, dict)}
            added: list[dict] = [
                {"path": p, "confidence": _PROPAGATED_CONFIDENCE}
                for p in sorted(communities.get(key, set()))
                if p not in existing
            ][:_MAX_GRAPH_ADD]  # 1 機能への流入を上限化（blob を丸ごと吸収させない）
            if added:
                c["files"] = members + added
        trace.append(f"graph-community expansion over {len(effective_edges)} edges (<= {_MAX_GRAPH_ADD}/feature)")

    # 各機能に最低 _MIN_FEATURE_FILES を保証（未割当の同一ディレクトリ・ファイルで best-effort 補完）。
    _backfill_features(clusters, source_paths)

    feature_count = 0
    file_count = 0
    for c in clusters:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "").strip()
        name = str(c.get("name") or "").strip() or key
        if not key:
            continue
        # canonical 済み members を dedup（最大 confidence）。実ファイル 0 件＝幻の機能は永続化しない。
        entries: dict[str, float] = {}
        for f in c.get("files") or []:
            if not isinstance(f, dict):
                continue
            fp = str(f.get("path") or "")
            if fp not in valid_paths:
                continue
            try:
                conf = float(f.get("confidence", 1.0))
            except (TypeError, ValueError):
                conf = 1.0
            if fp not in entries or conf > entries[fp]:
                entries[fp] = conf
        if not entries:
            continue
        feature_id = await _upsert_feature(
            session,
            run_id=run.id,
            project_id=project_id,
            key=key,
            name=name,
            description=str(c.get("description") or ""),
        )
        feature_count += 1
        for fp, confidence in entries.items():
            await _upsert_feature_file(
                session, run_id=run.id, feature_id=feature_id, file_path=fp, confidence=confidence
            )
            file_count += 1

    run.status = JobStatus.COMPLETED
    session.add(run)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)
    # 再解析で古い run の feature/feature_file が溜まるのを防ぐ（最新 run のみ残す）。
    await prune_superseded_runs(
        session, project_id=run.project_id, kind=JobType.FEATURE_CLUSTERING.value, keep_run_id=run.id
    )
    trace.append(f"clustered {feature_count} features over {file_count} file memberships")

    logger.info(
        "feature_clustering: %s features / %s memberships for %s/%s@%s",
        feature_count,
        file_count,
        request.owner,
        request.repo,
        commit_sha,
    )
    return FeatureClusteringResult(
        job_id=request.job_id,
        job_type=JobType.FEATURE_CLUSTERING,
        status=ResultStatus.COMPLETED,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        feature_count=feature_count,
        file_count=file_count,
        trace=trace,
    )
