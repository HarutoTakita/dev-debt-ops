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

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.pipelines.run_cleanup import prune_superseded_runs
from service.services import code_analysis, feature_authoring, feature_communities
from service.services.dependency_extraction import extract_dependencies
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, Feature, FeatureFile
from shared.pipelines.context import PipelineContext
from shared.schemas.feature_clustering import FeatureClusteringRequest, FeatureClusteringResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_PROPAGATED_CONFIDENCE = 0.5  # confidence for files added by graph-community propagation (vs LLM-asserted)
_BACKFILL_CONFIDENCE = 0.3  # confidence for files added by directory backfill (weakest signal)
_MIN_FEATURE_FILES = 3  # 各機能に最低これだけ実ファイルを割り当てる（"複数" を保証。近傍で best-effort 補完）


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


async def process(
    request: FeatureClusteringRequest,
    ctx: PipelineContext,
    *,
    clusters: list[dict] | None = None,
    graph_edges: list[tuple[str, str]] | None = None,
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
    """
    if ctx.session is None:
        raise RuntimeError("feature_clustering pipeline requires a DB session in the pipeline context")
    session = ctx.session
    trace: list[str] = []
    from_base = clusters is not None

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        # kc_analysis と同じ選定（round-robin・.svelte/.vue 含む・同一上限）で同一ファイル集合を対象にする。
        # 従来は is_source_file(py/ts/js のみ)+単純 [:N] 打ち切りで、KC とは別母集合（backend のみ）を
        # クラスタリングしていたため、機能フィルタ時に KC 未採点＝未着手(灰)ばかりになっていた。
        source_paths = code_analysis.select_source_paths(
            [t.path for t in tree if t.type == "blob"], config.analysis_max_files()
        )
        files: dict[str, str] = {}
        if not from_base:
            # File contents are only needed to build the import graph that feeds the clustering model.
            for path in source_paths:
                fc = await client.get_file_content(request.owner, request.repo, path, request.branch)
                if fc.content is not None:
                    files[path] = fc.content
        commits = await client.list_commits(request.owner, request.repo, sha=request.branch, per_page=1)
        commit_sha = commits[0].sha if commits else ""
    finally:
        if shared_client is None:
            await client.aclose()
    trace.append(f"fetched {len(source_paths)} source files")

    # Intra-repo import graph (main clustering signal) — only when we run the clustering model.
    edges: list[tuple[str, str]] = []
    if not from_base:
        repo_paths = set(files)
        seen: set[tuple[str, str]] = set()
        for path, content in files.items():
            for edge in extract_dependencies(path, content, repo_paths):
                key = (edge.from_path, edge.to_path)
                if key not in seen:
                    seen.add(key)
                    edges.append(key)

    project_id = uuid.UUID(request.project_id)
    job_id = uuid.UUID(request.job_id)
    run = await _get_or_create_run(
        session, job_id=job_id, project_id=project_id, commit_sha=commit_sha, branch=request.branch
    )

    if from_base:
        # Format/persist the Base Analysis Agent's features (no model call).
        trace.append(f"using {len(clusters)} features from base analysis")
    else:
        # 機能クラスタリングはエージェント経由（保存ツール＋直呼びフォールバック, issue 263）。1 モデル呼び出し。
        clusters = await feature_authoring.cluster_features_agentic(
            source_paths, edges, owner=request.owner, repo=request.repo
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

    # Graph-community re-alignment (issue 293, 方針A): grow each feature along the repo call graph so
    # memberships match hub-centered communities and each feature covers a connected region of related
    # code (fixes "the filter leaves only 1–2 files"). Uses the CGC file_edges passed by the agentic
    # orchestrator (from_base), else the locally-built import graph (standalone). LLM labels/names are
    # kept; propagated files are added at a lower confidence.
    # CGC が file_edges を出せず graph_edges=[] のときも、ローカルで構築した import グラフ(edges)で
    # コミュニティ再整列を効かせる（`[] is not None` で空集合が採用され拡張が無効化されるのを防ぐ）。
    effective_edges = graph_edges or edges
    if effective_edges:
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
            ]
            if added:
                c["files"] = members + added
        trace.append(f"graph-community expansion over {len(effective_edges)} edges")

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
