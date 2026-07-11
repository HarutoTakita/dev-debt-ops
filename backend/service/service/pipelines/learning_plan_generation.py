"""learning-plan-generation pipeline (issue 035, redesigned in 068) — 2 sections.

A. code  — このリポジトリのコードを理解する具体ステップ。機能の代表ファイル（機能スコープ）または concept
   マッチ（概念スコープ）を素材に、Gemini が「何を・なぜ理解すべきか」の説明つきステップを生成
   （``origin="team"`` / ``section="code"``、リンクはリポジトリ内ファイル）。
B. stack — テックスタック解析（``tech_stacks``）の言語/フレームワーク/DB を素材に、Gemini が一般的な学習
   リソース（外部 https URL + 説明）を生成（``origin="external"`` / ``section="stack"``）。

A → B の順、各セクション内は priority 順で ``learning_resources`` + ``learning_steps`` を作り
``estimated_total_minutes`` を集計する。``shared.worker.run_task`` owns the Job lifecycle. Idempotent:
if the plan already has steps, skip (the whole build commits once, so a failed run leaves no partial steps).

``process`` = ``prepare_inputs`` (read-only, on the session) → ``generate`` (Gemini, session-free) →
``persist`` (flush-only, on the session). The three stages are exposed so the baseline fan-out
(``baseline_generation``) can run ``generate`` concurrently across features while keeping DB work serial.
"""

import asyncio
import logging
import posixpath
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services import learning_authoring
from service.services.code_analysis import implementation_excerpt, is_vendored_path
from service.services.code_walkthrough import build_walkthrough
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.analysis_scope import is_learnable_path
from shared.enums import JobType, ResultStatus
from shared.models import Feature, FeatureFile, LearningPlan, LearningResource, LearningStep, TechStack
from shared.pipelines.context import PipelineContext
from shared.schemas.learning_plan import LearningPlanGenerationRequest, LearningPlanGenerationResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_PRIORITY_RANK = {"required": 0, "recommended": 1, "supplementary": 2, "hands_on": 3}
_SOURCE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")
_MAX_TEAM = 12


def _learnable_code_files(paths: list[str]) -> list[str]:
    """Drop boilerplate (``__init__.py`` / ``__main__.py``) that has no implementation worth studying.

    The scope rule lives in ``shared.analysis_scope`` so the galaxy map labels the same files 対象外
    (``out_of_scope``) rather than 未着手 — one source of truth, no drift.
    """
    return [p for p in paths if is_learnable_path(p)]


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


def _age_days(authored_at: str, *, now: datetime) -> int | None:
    if not authored_at:
        return None
    try:
        return max(0, (now - datetime.fromisoformat(authored_at.replace("Z", "+00:00"))).days)
    except ValueError:
        return None


async def _internal_assets(
    client: GitHubGitClient, repo_full_name: str, branch: str, gap_concepts: list[str], now: datetime
) -> list[dict]:
    """Find ADR + concept-matching code team assets with dormant_days."""
    owner, _, repo = repo_full_name.partition("/")
    if not owner or not repo:
        return []
    tree = await client.get_repository_tree(owner, repo, branch)
    blobs = [t.path for t in tree if t.type == "blob" and not is_vendored_path(t.path)]
    concepts = [c.lower() for c in gap_concepts]

    picked: dict[str, dict] = {}  # path → resource (dedup)
    for path in blobs:
        lower = path.lower()
        is_adr = "adr" in lower and lower.endswith(".md")
        is_code_match = lower.endswith(_SOURCE_EXTS) and any(c and c in lower for c in concepts)
        if not (is_adr or is_code_match):
            continue
        picked[path] = {
            "origin": "team",
            "kind": "adr" if is_adr else "code",
            # ADR は文書名が意味を持つのでファイル名のまま。コードは学習タイトルにする（issue 280）。
            "title": path.rsplit("/", 1)[-1] if is_adr else _code_title(path),
            "source_ref": path,
            "url": None,
            "estimated_minutes": 15 if is_adr else 20,
            "priority": "required" if is_adr else "hands_on",
        }
        if len(picked) >= _MAX_TEAM:
            break

    resources = list(picked.values())
    for r in resources:  # dormant_days from latest commit of the file
        commits = await client.list_commits(owner, repo, path=r["source_ref"], sha=branch, per_page=1)
        r["dormant_days"] = _age_days(commits[0].authored_at, now=now) if commits else None
    return resources


async def _feature_file_paths(session: AsyncSession, feature_id: uuid.UUID, *, limit: int = _MAX_TEAM) -> list[str]:
    """Representative file paths for a feature (top by clustering confidence) — Section A source (issue 068)."""
    files = (
        (
            await session.execute(
                select(FeatureFile)
                .where(col(FeatureFile.feature_id) == feature_id)
                .order_by(col(FeatureFile.confidence).desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [ff.file_path for ff in files]


_MAX_LEARN_CODE_FILES = 6  # 学習ステップ生成の素材として内容（抜粋）を渡す主要ファイル数の上限
_MAX_LEARN_CODE_CHARS = 2500  # 1 ファイルあたりの抜粋上限（プロンプト肥大を防ぐ）


async def _code_blocks(client: GitHubGitClient, owner: str, repo: str, branch: str, paths: list[str]) -> str:
    """Fetch the feature's main files and build ``=== path ===`` excerpt blocks for the authoring prompt.

    Grounds the step author in **real code across the feature's main files** (not just path names), so the
    plan explains the file group rather than restating filenames. Best-effort: unfetchable/empty files are
    skipped. Mirrors the quiz's ``_feature_content`` material assembly (issue 054/068).
    """
    blocks: list[str] = []
    for path in paths[:_MAX_LEARN_CODE_FILES]:
        try:
            fc = await client.get_file_content(owner, repo, path, branch)
        except Exception:
            continue
        body = fc.content or ""
        if not body.strip():
            continue
        excerpt = implementation_excerpt(body)
        if len(excerpt) > _MAX_LEARN_CODE_CHARS:
            excerpt = excerpt[:_MAX_LEARN_CODE_CHARS] + "\n... (truncated)"
        blocks.append(f"=== {path} ===\n{excerpt}")
    return "\n\n".join(blocks)


# フロントの resourceKindSchema と一致させる許可 kind。LLM が想定外の値（例: priority の "hands_on"）を
# kind に混入させても保存しないよう、許可外は "docs" に丸める（フロントの parse 失敗→500 を防ぐ）。
_VALID_KINDS = frozenset({"adr", "video", "pr_comment", "wiki", "docs", "book", "article", "code"})


def _code_title(path: str) -> str:
    """A learning-oriented fallback title derived from a path (never the bare file name, issue 280)."""
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] or name
    return f"{stem} の実装を理解する"


def _clean_step_title(title: object, path: str) -> str:
    """Use the model's title, but replace it with a learning title if it's empty or just the file name/path."""
    t = str(title or "").strip()
    name = path.rsplit("/", 1)[-1]
    if not t or t in (name, path) or t.lower().endswith(_SOURCE_EXTS):
        return _code_title(path)
    return t


def _match_code_file(sr: object, norm_to_canon: dict[str, str], base_to_canon: dict[str, list[str]]) -> str | None:
    """Resolve a model-returned ``source_ref`` to a canonical repo path (issue 074-C).

    Exact-set membership dropped every step on any path-format drift (``./`` prefix, separators,
    repo- vs feature-relative). Normalize via ``posixpath.normpath`` first, then fall back to a
    *uniquely* matching basename so near-miss paths keep their Gemini explanations. Returns ``None``
    when it can't be resolved (so it's skipped, not mismapped to the wrong file).
    """
    if not isinstance(sr, str) or not sr:
        return None
    canon = norm_to_canon.get(posixpath.normpath(sr))
    if canon is not None:
        return canon
    candidates = base_to_canon.get(sr.rsplit("/", 1)[-1], [])
    return candidates[0] if len(candidates) == 1 else None


def _code_resources(steps: list[dict], code_files: list[str]) -> list[dict]:
    """Map Gemini code-learning steps to Section A (code) resources; fall back to listing files when empty."""
    norm_to_canon = {posixpath.normpath(p): p for p in code_files}
    base_to_canon: dict[str, list[str]] = {}
    for p in code_files:
        base_to_canon.setdefault(p.rsplit("/", 1)[-1], []).append(p)
    out: list[dict] = []
    seen: set[str] = set()
    for s in steps:
        sr = _match_code_file(s.get("source_ref"), norm_to_canon, base_to_canon)
        if sr is None or sr in seen:
            continue
        seen.add(sr)
        out.append(
            {
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": _clean_step_title(s.get("title"), sr),
                "summary": str(s.get("summary") or ""),
                "source_ref": sr,
                "url": None,
                "estimated_minutes": s.get("estimated_minutes") if isinstance(s.get("estimated_minutes"), int) else 15,
                "priority": s.get("priority") if s.get("priority") in _PRIORITY_RANK else "required",
                "dormant_days": None,
            }
        )
    if not out:  # フォールバック: 説明生成が無くても読む対象は提示する
        out = [
            {
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": _code_title(sr),
                "summary": "",
                "source_ref": sr,
                "url": None,
                "estimated_minutes": 15,
                "priority": "required",
                "dormant_days": None,
            }
            for sr in code_files[:_MAX_TEAM]
        ]
    return out


def _stack_resources(raw: list[dict]) -> list[dict]:
    """Map Gemini stack-learning items to Section B (stack) resources (https URLs only)."""
    out: list[dict] = []
    for item in raw:
        url = item.get("url")
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
            continue
        out.append(
            {
                "origin": "external",
                "section": "stack",
                "kind": item.get("kind") if item.get("kind") in _VALID_KINDS else "docs",
                "title": str(item.get("title") or "External resource"),
                "summary": str(item.get("summary") or ""),
                "tech": str(item.get("tech") or ""),
                "source_ref": None,
                "url": url,
                "estimated_minutes": item.get("estimated_minutes")
                if isinstance(item.get("estimated_minutes"), int)
                else None,
                "priority": item.get("priority") if item.get("priority") in _PRIORITY_RANK else "recommended",
                "dormant_days": None,
            }
        )
    return out


async def _stack_terms(session: AsyncSession, repo_full_name: str, *, limit: int = 10) -> list[str]:
    """Tech terms (languages + categories) from the project's tech_stack — Section B source (issue 068)."""
    owner, _, repo = repo_full_name.partition("/")
    if not owner or not repo:
        return []
    ts = (
        await session.execute(select(TechStack).where(col(TechStack.owner) == owner, col(TechStack.repo) == repo))
    ).scalar_one_or_none()
    if ts is None:
        return []
    terms: list[str] = [x["name"] for x in ts.languages if isinstance(x, dict) and x.get("name")]
    if isinstance(ts.categories, dict):
        for items in ts.categories.values():
            if isinstance(items, list):
                terms += [x["name"] for x in items if isinstance(x, dict) and x.get("name")]
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:limit]


async def _pregenerate_walkthroughs(
    session: AsyncSession,
    request: LearningPlanGenerationRequest,
    code_to_walk: list[tuple[LearningResource, str]],
    shared_client: GitHubGitClient | None = None,
) -> None:
    """Pre-generate + persist line-anchored walkthroughs for the plan's code files (concurrent, capped).

    Network/Gemini work runs concurrently (semaphore-capped); the session is only touched serially after.
    A file that comes back empty — a transient Gemini rate-limit during the concurrent burst, a fetch
    error, or genuinely no steps — is **retried once serially**; the burst is over by then, so a calmer
    pass usually recovers it, and a still-empty walkthrough is **logged** (never silently swallowed) so it
    is diagnosable rather than an invisible dead-end. Reuses ``shared_client`` when given, else mints its own.
    """
    if not code_to_walk:
        return
    owner, _, repo = request.repo_full_name.partition("/")
    if not owner or not repo:
        return
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    sem = asyncio.Semaphore(5)

    async def _walk(resource: LearningResource, path: str) -> None:
        async with sem:
            try:
                resource.walkthrough = await build_walkthrough(client, owner, repo, path, request.branch)
            except Exception:  # build_walkthrough degrades to [] internally; guard only the unexpected
                logger.exception("code-walkthrough pre-generation errored for %s", path)
                resource.walkthrough = []

    try:
        await asyncio.gather(*(_walk(res, path) for res, path in code_to_walk))
        # Retry (serially, in a calmer window) the files that came back empty — most empties are transient
        # Gemini rate-limits during the concurrent burst. A genuinely empty file simply stays empty.
        for resource, path in [(res, p) for res, p in code_to_walk if not res.walkthrough]:
            try:
                resource.walkthrough = await build_walkthrough(client, owner, repo, path, request.branch)
            except Exception:
                logger.exception("code-walkthrough retry errored for %s", path)
            if not resource.walkthrough:
                logger.warning(
                    "code-walkthrough still empty after retry: %s/%s@%s %s", owner, repo, request.branch, path
                )
    finally:
        if shared_client is None:
            await client.aclose()
    for resource, _path in code_to_walk:
        session.add(resource)


@dataclass
class PlanInputs:
    """Read-only inputs for learning-plan generation, gathered before the Gemini step."""

    code_name: str
    code_desc: str
    code_files: list[str]
    code_blocks: str  # 主要ファイルのコード抜粋（=== path === 区切り）。ステップ生成の素材
    terms: list[str]
    owner: str
    repo: str


@dataclass
class PlanGenerated:
    """Gemini authoring output (produced without touching the DB session — safe to run concurrently)."""

    code_steps: list[dict]
    stack_raw: list[dict]


async def prepare_inputs(
    session: AsyncSession,
    ctx: PipelineContext,
    *,
    feature: Feature | None,
    repo_full_name: str,
    branch: str,
    github: GitHubRef,
    gap_concepts: list[str],
) -> PlanInputs:
    """Gather the plan's generation inputs (code files + name/desc + stack terms). Read-only — no writes.

    Feature scope uses the feature's representative files; concept scope resolves ADR/concept-matching
    files from the repo tree. Safe to run before the concurrent ``generate`` step.
    """
    now = datetime.now(UTC)
    owner, _, repo = repo_full_name.partition("/")
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(github))
    try:
        if feature is not None:
            code_files = await _feature_file_paths(session, feature.id)
            code_name, code_desc = feature.name, feature.description
        else:
            assets = await _internal_assets(client, repo_full_name, branch, gap_concepts, now)
            code_files = [r["source_ref"] for r in assets if r.get("source_ref")]
            code_name = gap_concepts[0] if gap_concepts else "コード理解"
            code_desc = ""
        # __init__.py / __main__.py を学習対象から除外（Gemini 入力・マッチング/フォールバック双方に効く）。
        code_files = _learnable_code_files(code_files)
        # ステップ生成 LLM に「パスだけでなく実コード抜粋」を渡し、機能の複数ファイルを横断して解説させる。
        code_blocks = await _code_blocks(client, owner, repo, branch, code_files)
    finally:
        if shared_client is None:
            await client.aclose()
    terms = await _stack_terms(session, repo_full_name)
    return PlanInputs(code_name, code_desc, code_files, code_blocks, terms, owner, repo)


async def generate(inputs: PlanInputs) -> PlanGenerated:
    """Gemini authoring for a learning plan (no DB access → safe to run concurrently across features).

    Falls back to an empty section when Gemini is unavailable, exactly as the sequential path did.
    """
    try:
        code_steps = await learning_authoring.generate_code_learning_steps_agentic(
            inputs.code_name,
            inputs.code_desc,
            inputs.code_files,
            owner=inputs.owner,
            repo=inputs.repo,
            code_blocks=inputs.code_blocks,
        )
    except ValueError:
        logger.warning("Gemini code-learning unavailable; listing files without explanations")
        code_steps = []
    try:
        stack_raw = await learning_authoring.generate_external_resources_agentic(
            inputs.terms, owner=inputs.owner, repo=inputs.repo
        )
    except ValueError:
        logger.warning("Gemini stack-learning unavailable; code section only")
        stack_raw = []
    return PlanGenerated(code_steps, stack_raw)


async def persist(
    session: AsyncSession,
    request: LearningPlanGenerationRequest,
    ctx: PipelineContext,
    inputs: PlanInputs,
    generated: PlanGenerated,
    *,
    plan: LearningPlan,
) -> tuple[int, int, int]:
    """Build the plan's resources + ordered steps + walkthroughs on ``session`` (flush only).

    Returns ``(step_count, team_count, external_count)``. ``plan`` must already be flushed (has an id).
    """
    code = _code_resources(generated.code_steps, inputs.code_files)
    stack = _stack_resources(generated.stack_raw)
    # A（code）→ B（stack）の順。各セクション内は priority 順。
    ordered = sorted(code, key=lambda r: _PRIORITY_RANK.get(r["priority"], 9)) + sorted(
        stack, key=lambda r: _PRIORITY_RANK.get(r["priority"], 9)
    )

    total_minutes = 0
    code_to_walk: list[tuple[LearningResource, str]] = []
    for order, r in enumerate(ordered):
        resource = LearningResource(
            project_id=plan.project_id,
            origin=r["origin"],
            section=r["section"],
            kind=r["kind"],
            title=r["title"],
            summary=r["summary"],
            tech=r.get("tech", ""),
            source_ref=r["source_ref"],
            url=r["url"],
            estimated_minutes=r["estimated_minutes"],
            priority=r["priority"],
            dormant_days=r["dormant_days"],
        )
        session.add(resource)
        await session.flush()
        session.add(LearningStep(plan_id=plan.id, order=order, completed=False, resource_id=resource.id))
        total_minutes += r["estimated_minutes"] or 0
        if r["section"] == "code" and r["kind"] == "code" and isinstance(r["source_ref"], str):
            code_to_walk.append((resource, r["source_ref"]))

    # 解析時に各コードファイルの行ごと解説（walkthrough）を事前生成し保存する（ユーザーが開いた瞬間に即表示）。
    await _pregenerate_walkthroughs(session, request, code_to_walk, shared_client=ctx.github_client)

    plan.estimated_total_minutes = total_minutes
    session.add(plan)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)

    logger.info(
        "learning_plan_generation: %s steps (code=%s stack=%s) for plan %s",
        len(ordered),
        len(code),
        len(stack),
        request.plan_id,
    )
    return len(ordered), len(code), len(stack)


async def process(request: LearningPlanGenerationRequest, ctx: PipelineContext) -> LearningPlanGenerationResult:
    """Generate the plan's resources + ordered steps (team-first): prepare → generate → persist."""
    if ctx.session is None:
        raise RuntimeError("learning_plan_generation pipeline requires a DB session in the pipeline context")
    session = ctx.session
    plan_id = uuid.UUID(request.plan_id)

    plan = (await session.execute(select(LearningPlan).where(col(LearningPlan.id) == plan_id))).scalar_one_or_none()
    if plan is None:
        return _result(request, step_count=0, team=0, external=0)
    existing = (
        await session.execute(
            select(func.count()).select_from(LearningStep).where(col(LearningStep.plan_id) == plan_id)
        )
    ).scalar_one()
    if existing:  # idempotent: already generated
        return _result(request, step_count=existing, team=0, external=0)

    feature = None
    if plan.feature_id is not None:
        feature = (
            await session.execute(select(Feature).where(col(Feature.id) == plan.feature_id))
        ).scalar_one_or_none()

    inputs = await prepare_inputs(
        session,
        ctx,
        feature=feature,
        repo_full_name=request.repo_full_name,
        branch=request.branch,
        github=request.github,
        gap_concepts=request.gap_concepts,
    )
    generated = await generate(inputs)
    step_count, team, external = await persist(session, request, ctx, inputs, generated, plan=plan)
    return _result(request, step_count=step_count, team=team, external=external)


def _result(
    request: LearningPlanGenerationRequest, *, step_count: int, team: int, external: int
) -> LearningPlanGenerationResult:
    return LearningPlanGenerationResult(
        job_id=request.job_id,
        job_type=JobType.LEARNING_PLAN_GENERATION,
        status=ResultStatus.COMPLETED,
        plan_id=request.plan_id,
        step_count=step_count,
        team_count=team,
        external_count=external,
    )
