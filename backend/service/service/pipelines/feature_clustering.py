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
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services import code_analysis, feature_authoring
from service.services.dependency_extraction import extract_dependencies
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, Feature, FeatureFile
from shared.pipelines.context import PipelineContext
from shared.schemas.feature_clustering import FeatureClusteringRequest, FeatureClusteringResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_MAX_FILES = 200  # cap files fetched/clustered per run (REST + prompt budget; MVP)


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


async def process(request: FeatureClusteringRequest, ctx: PipelineContext) -> FeatureClusteringResult:
    """Cluster the repository's source files into features and upsert them under an analysis run."""
    if ctx.session is None:
        raise RuntimeError("feature_clustering pipeline requires a DB session in the pipeline context")
    session = ctx.session
    trace: list[str] = []

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        source_paths = [t.path for t in tree if t.type == "blob" and code_analysis.is_source_file(t.path)][:_MAX_FILES]
        files: dict[str, str] = {}
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

    # Intra-repo import graph (main clustering signal).
    repo_paths = set(files)
    edges: list[tuple[str, str]] = []
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

    # 機能クラスタリングはエージェント経由（保存ツール＋直呼びフォールバック, issue 263）。1 モデル呼び出し。
    clusters = await feature_authoring.cluster_features_agentic(
        source_paths, edges, owner=request.owner, repo=request.repo
    )
    valid_paths = set(source_paths)
    feature_count = 0
    file_count = 0
    for c in clusters:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "").strip()
        name = str(c.get("name") or "").strip() or key
        if not key:
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
        files_val = c.get("files")
        members = files_val if isinstance(files_val, list) else []
        for f in members:
            if not isinstance(f, dict):
                continue
            fp = str(f.get("path") or "")
            if fp not in valid_paths:
                continue  # only accept files that actually exist in the tree
            try:
                confidence = float(f.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 1.0
            await _upsert_feature_file(
                session, run_id=run.id, feature_id=feature_id, file_path=fp, confidence=confidence
            )
            file_count += 1

    run.status = JobStatus.COMPLETED
    session.add(run)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)
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
