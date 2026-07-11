"""agentic-analysis pipeline (issue 069 → 266) — agent-first repository analysis.

``shared.worker.run_task`` owns the ``Job`` lifecycle (PROCESSING → COMPLETED/FAILED,
idempotency) and writes the returned result into ``Job.result_data``.

Agent-first re-architecture (issue 266): the main repository analysis IS an agent. The pipeline runs
as a sequence of *blocks*:

1. **Base Analysis Agent (block 0)** — the ADK ``run_analysis_agent`` runs FIRST, using the
   exploration MCP toolsets (Serena / GitHub / CodeGraphContext) to produce ONE qualitative
   ``BaseAnalysis`` (features / key concepts / code & knowledge risk narrative), persisted to
   ``base_analysis_snapshots``. This is the "元データ" downstream blocks are meant to consume.
2. **Deterministic backbone** — the existing detection/analysis pipelines (feature clustering →
   code debt → KC → knowledge debt → stack → baseline). Each creates its own ``analysis_run`` keyed
   by ``(job_id, kind)`` and upserts its tables so the Matrix / Galaxy maps populate. All pipelines
   only ``flush``; ``run_task`` commits once.

PR1 (issue 266) is additive: the base agent runs first and its output is persisted, but the
deterministic backbone still fully produces the screen tables (source-of-truth unchanged). Later PRs
make the backbone blocks *consume* ``base_analysis``. A failed/empty base agent never aborts the run
— the deterministic backbone still completes the analysis (graceful degradation).

GitHub token is method B (minted from the Secret Manager-backed App key); Vertex AI uses ADC.
"""

import logging
import shutil
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.agents.budget import RunBudget
from service.agents.runner import run_analysis_agent
from service.pipelines import (
    baseline_generation,
    code_debt_detection,
    feature_clustering,
    kc_analysis,
    knowledge_debt_detection,
    stack_analysis,
)
from service.pipelines.progress import AGENTIC_STEPS, ProgressReporter
from service.services import code_graph, function_graph, repo_checkout, trivy_scan
from service.services.github_app import GitHubAppService
from service.services.github_git_client import CachingGitHubGitClient, GitHubGitClient, LocalCloneGitHubClient
from shared.enums import JobType, ResultStatus
from shared.models import AnalysisRun, BaseAnalysisSnapshot, CodeDebt, CodeGraph, DebtTrendPoint, FileKc
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest, AgenticAnalysisResult
from shared.schemas.base_analysis import BaseAnalysis
from shared.schemas.code_debt_detection import CodeDebtDetectionRequest
from shared.schemas.feature_clustering import FeatureClusteringRequest
from shared.schemas.kc_analysis import KcAnalysisRequest
from shared.schemas.knowledge_debt_detection import KnowledgeDebtDetectionRequest
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    """Resolve a GitHub installation token (method B: mint from the Secret Manager key)."""
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def _persist_code_graph(session: AsyncSession, project_id: str, graph: dict) -> None:
    """Upsert the project's latest CodeGraphContext snapshot (issue 235). Flush only; run_task commits."""
    now = datetime.now(UTC)
    pid = uuid.UUID(project_id)
    stmt = pg_insert(CodeGraph).values(id=uuid.uuid4(), project_id=pid, computed_at=now, graph=graph)
    stmt = stmt.on_conflict_do_update(constraint="uq_code_graphs_project", set_={"computed_at": now, "graph": graph})
    await session.execute(stmt)
    await session.flush()


async def _persist_base_analysis(session: AsyncSession, project_id: str, base: BaseAnalysis) -> None:
    """Upsert the project's latest Base Analysis Agent output (issue 266). Flush only; run_task commits."""
    now = datetime.now(UTC)
    pid = uuid.UUID(project_id)
    payload = base.model_dump()
    stmt = pg_insert(BaseAnalysisSnapshot).values(id=uuid.uuid4(), project_id=pid, computed_at=now, payload=payload)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_base_analysis_snapshots_project", set_={"computed_at": now, "payload": payload}
    )
    await session.execute(stmt)
    await session.flush()


async def _run_id_for_job(session: AsyncSession, job_id: str, kind: str) -> uuid.UUID | None:
    """The ``analysis_run`` this job created for ``kind`` (runs are keyed by ``(job_id, kind)``)."""
    row = (
        await session.execute(
            select(AnalysisRun).where(col(AnalysisRun.job_id) == uuid.UUID(job_id), col(AnalysisRun.kind) == kind)
        )
    ).scalar_one_or_none()
    return row.id if row is not None else None


async def _record_trend_point(session: AsyncSession, request: AgenticAnalysisRequest) -> None:
    """Append one debt-trend point from THIS run's aggregates (issue 067). Flush only; run_task commits.

    サーバー側でブラウザ非依存に記録する。従来はフロントの fire-and-forget（POST /trend-snapshot、タブ
    依存）だけが記録していたため、タブを閉じる / API 起点の解析だと推移が 1 点も残らず、ダッシュボードが
    常に空状態（「解析を実行すると…」）を表示していた。

    集計は api ``debt_query.build_overview`` / ``record_trend_snapshot`` の母集合セマンティクスに合わせる:
    KC が採点した全ファイルを母集合とし（KC 未実行時のみ code-debt ファイル集合にフォールバック）、その平均
    ``code_debt_score``（ファイルごとの最大 finding スコア、無ければ 0）と平均 ``knowledge_coverage``。
    """
    pid = uuid.UUID(request.project_id)
    code_run = await _run_id_for_job(session, request.job_id, JobType.CODE_DEBT_DETECTION.value)
    kc_run = await _run_id_for_job(session, request.job_id, JobType.KC_ANALYSIS.value)

    code_score: dict[str, float] = {}
    if code_run is not None:
        rows = (await session.execute(select(CodeDebt).where(col(CodeDebt.run_id) == code_run))).scalars().all()
        for r in rows:
            code_score[r.file_path] = max(code_score.get(r.file_path, 0.0), r.code_debt_score)

    kc_map: dict[str, float] = {}
    if kc_run is not None:
        rows = (
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
        for r in rows:
            kc_map[r.file_path] = r.kc

    # 母集合は KC 採点ファイル（各点が実 KC を持つ）。KC 未実行時のみ code-debt ファイルにフォールバック。
    universe = sorted(kc_map) if kc_map else sorted(code_score)
    if not universe:
        return  # 何も解析されていない → 記録しない（空状態のまま）
    n = len(universe)
    code = sum(code_score.get(p, 0.0) for p in universe) / n
    kc = sum(kc_map.get(p, 0.0) for p in universe) / n
    # 解析実行ごとに 1 点（ISO タイムスタンプをキー兼ラベルに）。同一 project×week の再実行は upsert。
    week = datetime.now(UTC).isoformat()
    stmt = pg_insert(DebtTrendPoint).values(
        id=uuid.uuid4(), project_id=pid, week=week, code_debt_score=code, knowledge_coverage=kc
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_debt_trend_points_project_week",
        set_={"code_debt_score": code, "knowledge_coverage": kc},
    )
    await session.execute(stmt)
    await session.flush()


async def _run_backbone_step(
    name: str,
    run: Callable[[], Awaitable[object]],
    steps: list[str],
    reporter: ProgressReporter | None = None,
) -> None:
    """Run one backbone sub-pipeline; record success/failure (a failure never aborts the run).

    ``name`` doubles as the progress step key (matches ``AGENTIC_STEPS``), so the reporter reflects
    each step's running → completed/failed transition for the live cockpit.
    """
    if reporter is not None:
        await reporter.start(name)
    try:
        await run()
        steps.append(f"[backbone] {name} done")
        if reporter is not None:
            await reporter.complete(name)
    except Exception as exc:
        logger.exception("agentic backbone step failed: %s", name)
        steps.append(f"[backbone] {name} failed: {exc}")
        if reporter is not None:
            await reporter.fail(name)


async def process(request: AgenticAnalysisRequest, ctx: PipelineContext) -> AgenticAnalysisResult:
    """Run the Base Analysis Agent (block 0) then the deterministic backbone (produces map data)."""
    if ctx.session is None:
        raise RuntimeError("agentic_analysis pipeline requires a DB session in the pipeline context")

    steps: list[str] = []
    reporter = ProgressReporter(request.job_id, AGENTIC_STEPS)
    session = ctx.session

    # 1) Base Analysis Agent — the FIRST block (agent-first, issue 266). Shallow-clone so the agent
    # can navigate the repo via Serena (LSP); a failed clone just disables Serena. A failed/empty run
    # never aborts the analysis — the deterministic backbone below still produces the screen tables.
    await reporter.start("base_analysis")
    agent_trace: list[str] = []
    base_analysis = BaseAnalysis()
    budget = RunBudget()
    token = await _mint_installation_token(request.github)

    # 長時間 run（clone+エージェント+バックボーン+機能別生成）が ~1h のトークン TTL を超えても 401 で止まらないよう、
    # 401 時に再発行するプロバイダを渡す（issue 078-D）。
    async def _refresh_token() -> str:
        return await _mint_installation_token(request.github)

    client = GitHubGitClient(access_token=token, token_provider=_refresh_token)
    # clone から run_analysis_agent までを 1 つの try/finally で囲む（issue 078-C）。以前は clone の後・try の前で
    # グラフ構築 / _persist_code_graph(DB) / Trivy が未ガードに走り、そこで例外が出るとクローン＋git クライアントが
    # 残留していた。repo_dir/trivy_findings は try 前に初期化し、finally が全経路で cleanup する。
    repo_dir: str | None = None
    trivy_findings: list[trivy_scan.TrivyAggregate] = []
    try:
        repo_dir = await repo_checkout.shallow_clone(request.owner, request.repo, request.branch, token)
        # マクロ俯瞰用のコードグラフを事前構築（issue 235）。失敗してもグラフ無しで継続（graceful）。CGC スナップ
        # ショット＋clone からの決定的スナップショット（issue 250）をマージし、CGC が索引失敗/関数 0 件でも理解度
        # マップの L2/L3 が「どんな repo でも」表示される。マージ結果が空＝一時的失敗のときは上書きせず前回を温存。
        cgc_snapshot: dict = {}
        if repo_dir is not None and await code_graph.build_graph(repo_dir):
            cgc_snapshot = await code_graph.extract_snapshot(repo_dir)
        det_snapshot = function_graph.build_snapshot(function_graph.read_repo_sources(repo_dir)) if repo_dir else {}
        snapshot = code_graph.merge_snapshots(cgc_snapshot, det_snapshot)
        if snapshot:
            await _persist_code_graph(session, request.project_id, snapshot)
        # Trivy SCA/secret/misconfig (issue 278): a deterministic scan over the SAME clone (no extra
        # checkout). Runs regardless of the agent outcome; graceful []. Fed into the code-debt block below.
        trivy_findings = await trivy_scan.scan_repo(repo_dir) if repo_dir else []
        agent_trace, base_analysis = await run_analysis_agent(
            client=client,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            budget=budget,
            repo_dir=repo_dir,
            github_token=token,
        )
        if not base_analysis.is_empty():
            await _persist_base_analysis(session, request.project_id, base_analysis)
        await reporter.complete("base_analysis")
    except Exception as exc:
        # ベース解析（＋事前のグラフ/Trivy）はベストエフォート。Gemini の一時障害やツール/グラフ/クローン失敗で
        # 例外化しても、決定的バックボーン（機能/コード負債/理解度/学習・クイズ）まで失わせない（run_task の全 flush
        # ロールバック＝解析全体 FAILED を避ける）。ログを残し、元データ無しで続行し COMPLETED に確定する。
        logger.exception("base analysis / pre-analysis step failed; continuing with the deterministic backbone")
        agent_trace = [f"[analysis_agent] failed: {exc}"]
        base_analysis = BaseAnalysis()
        await reporter.fail("base_analysis")
    finally:
        # エージェント用クライアントは閉じるが、clone は消さない — バックボーンがローカル読み取りに再利用する
        # （下記）。clone / per-run KuzuDB の削除は解析完了後の最終 finally に集約した。
        await client.aclose()

    # 2) Deterministic backbone — each sub-pipeline runs under THIS job_id, creating its own
    # (job_id, kind) run and upserting its tables on the shared session (flush only). Order:
    # feature clustering first (learning/quiz depend on it), then code debt, KC, knowledge debt.
    # 取得の共通化: バックボーン全体で 1 つの読み取りキャッシュ付き GitHub クライアントを共有し、各ステップが
    # 個別に行っていたリポジトリツリー取得（〜5×）・重複するソースファイル取得を 1 回に集約する。標準呼び出し
    # （各パイプライン単体）では ctx.github_client は None のまま＝各自で取得する従来どおりの動作になる。
    # clone がある場合は LocalCloneGitHubClient でツリー/ファイル取得をローカルに向ける（Contents API の
    # per-file 呼び出し＝502 の主因・REST レート枠の大半を排除。blame/list_commits は API のまま＝浅い clone に
    # 履歴が無く、blame は別枠の GraphQL）。clone 失敗時は従来どおり API 版にフォールバック。
    try:
        # クライアント生成（トークンのミント含む）も try 内で行い、失敗しても finally が clone を回収する。
        stack_token = await _mint_installation_token(request.github)
        if repo_dir is not None:
            ctx.github_client = LocalCloneGitHubClient(
                repo_dir, access_token=stack_token, token_provider=_refresh_token
            )
        else:
            ctx.github_client = CachingGitHubGitClient(access_token=stack_token, token_provider=_refresh_token)
        fc_req = FeatureClusteringRequest(
            job_id=request.job_id,
            job_type=JobType.FEATURE_CLUSTERING,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            github=request.github,
            requested_by=request.requested_by,
            project_id=request.project_id,
        )
        # agent-first (issue 268): consume the Base Analysis Agent's features when present; else the
        # deterministic clustering runs as fallback (clusters=None). This is the "features" block.
        base_clusters = [f.model_dump() for f in base_analysis.features] or None
        # issue 293 (方針A): hand the repo call graph (CGC file_edges, already computed above) to the
        # clustering block so it re-aligns feature memberships to graph communities (seeded label
        # propagation). Empty/failed snapshot → [] → the block leaves memberships as the LLM authored.
        fc_graph_edges = [
            (e["source"], e["target"])
            for e in (snapshot.get("file_edges") or [])
            if isinstance(e, dict) and e.get("source") and e.get("target")
        ]
        await _run_backbone_step(
            "feature_clustering",
            lambda: feature_clustering.process(fc_req, ctx, clusters=base_clusters, graph_edges=fc_graph_edges),
            steps,
            reporter,
        )
        cd_req = CodeDebtDetectionRequest(
            job_id=request.job_id,
            job_type=JobType.CODE_DEBT_DETECTION,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            github=request.github,
            requested_by=request.requested_by,
            project_id=request.project_id,
        )
        # agent-first (issue 271): enrich deterministic code debts with the agent's rationale (notes
        # only; scores/severity stay deterministic). Empty base → base_findings=None (no change).
        base_code_findings = [f.model_dump() for f in base_analysis.code_findings] or None
        await _run_backbone_step(
            "code_debt_detection",
            lambda: code_debt_detection.process(
                cd_req, ctx, base_findings=base_code_findings, trivy_findings=trivy_findings
            ),
            steps,
            reporter,
        )
        kc_req = KcAnalysisRequest(
            job_id=request.job_id,
            job_type=JobType.KC_ANALYSIS,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            github=request.github,
            requested_by=request.requested_by,
            project_id=request.project_id,
        )
        await _run_backbone_step("kc_analysis", lambda: kc_analysis.process(kc_req, ctx), steps, reporter)
        kd_req = KnowledgeDebtDetectionRequest(
            job_id=request.job_id,
            job_type=JobType.KNOWLEDGE_DEBT_DETECTION,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            github=request.github,
            requested_by=request.requested_by,
            project_id=request.project_id,
        )
        # agent-first (issue 273): enrich deterministic knowledge debts with the agent's rationale
        # (detection_notes only; KC/coverage/scores stay deterministic). Empty base → None (no change).
        base_knowledge_findings = [f.model_dump() for f in base_analysis.knowledge_findings] or None
        await _run_backbone_step(
            "knowledge_debt_detection",
            lambda: knowledge_debt_detection.process(kd_req, ctx, base_findings=base_knowledge_findings),
            steps,
            reporter,
        )

        # Tech-stack detection (issue 068): populates ``tech_stacks`` (owner/repo keyed) so the learning
        # plan's "技術スタックを学ぶ" section has source terms. Must run before baseline generation below.
        # Use the *deterministic* populate (not the ADK stack agent, which sometimes skips save_stack).
        async def _populate_stack() -> None:
            await stack_analysis.populate_tech_stack(
                ctx.github_client, session, request.owner, request.repo, request.branch
            )

        await _run_backbone_step("stack_analysis", _populate_stack, steps, reporter)

        # 2b) Learning plans + baseline quizzes per feature (server-side, no browser orchestration).
        await reporter.start("baseline")

        async def _on_baseline_progress(done: int, total: int) -> None:
            await reporter.update("baseline", done=done, total=total)

        steps.extend(
            await baseline_generation.generate_learning_and_quizzes(request, ctx, on_progress=_on_baseline_progress)
        )
        await reporter.complete("baseline")

        # 2c) 推移点をサーバー側で記録（ブラウザ非依存, issue 067）。内部の永続化なのでトレースには出さない。
        # 失敗しても解析全体は止めない（推移が 1 点欠けるだけ）。
        try:
            await _record_trend_point(session, request)
        except Exception:
            logger.exception("trend snapshot recording failed (non-fatal)")
    finally:
        # 共有クライアントを必ず閉じ、clone / per-run KuzuDB（issue 078-A）をここで片付ける（バックボーンの
        # ローカル読み取りが終わるまで clone を生存させるため、cleanup をエージェントブロックから最終へ移動）。
        if ctx.github_client is not None:  # トークンのミント失敗などで未生成のことがある
            await ctx.github_client.aclose()
        ctx.github_client = None
        if repo_dir is not None:
            shutil.rmtree(repo_dir, ignore_errors=True)
            shutil.rmtree(code_graph.kuzudb_path_for(repo_dir), ignore_errors=True)

    all_trace = agent_trace + steps
    summary = agent_trace[-1] if agent_trace else (steps[-1] if steps else "analysis produced no trace")
    logger.info(
        "agentic_analysis done owner=%s repo=%s agent_trace=%d backbone=%d base(features=%d,code=%d,knowledge=%d)",
        request.owner,
        request.repo,
        len(agent_trace),
        len(steps),
        len(base_analysis.features),
        len(base_analysis.code_findings),
        len(base_analysis.knowledge_findings),
    )
    return AgenticAnalysisResult(
        job_id=request.job_id,
        job_type=JobType.AGENTIC_ANALYSIS,
        status=ResultStatus.COMPLETED,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        summary=summary,
        agent_trace=all_trace,
    )
