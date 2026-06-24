"""learning-plan-generation pipeline (issue 035, redesigned in 068) — 2 sections.

A. code  — このリポジトリのコードを理解する具体ステップ。機能の代表ファイル（機能スコープ）または concept
   マッチ（概念スコープ）を素材に、Gemini が「何を・なぜ理解すべきか」の説明つきステップを生成
   （``origin="team"`` / ``section="code"``、リンクはリポジトリ内ファイル）。
B. stack — テックスタック解析（``tech_stacks``）の言語/フレームワーク/DB を素材に、Gemini が一般的な学習
   リソース（外部 https URL + 説明）を生成（``origin="external"`` / ``section="stack"``）。

A → B の順、各セクション内は priority 順で ``learning_resources`` + ``learning_steps`` を作り
``estimated_total_minutes`` を集計する。``shared.worker.run_task`` owns the Job lifecycle. Idempotent:
if the plan already has steps, skip (the whole build commits once, so a failed run leaves no partial steps).
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services import gemini_stack_service
from service.services.code_analysis import is_vendored_path
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import Feature, FeatureFile, LearningPlan, LearningResource, LearningStep, TechStack
from shared.pipelines.context import PipelineContext
from shared.schemas.learning_plan import LearningPlanGenerationRequest, LearningPlanGenerationResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_PRIORITY_RANK = {"required": 0, "recommended": 1, "supplementary": 2, "hands_on": 3}
_SOURCE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")
_MAX_TEAM = 12


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
    client: GitHubGitClient, request: LearningPlanGenerationRequest, now: datetime
) -> list[dict]:
    """Find ADR + concept-matching code team assets with dormant_days."""
    owner, _, repo = request.repo_full_name.partition("/")
    if not owner or not repo:
        return []
    tree = await client.get_repository_tree(owner, repo, request.branch)
    blobs = [t.path for t in tree if t.type == "blob" and not is_vendored_path(t.path)]
    concepts = [c.lower() for c in request.gap_concepts]

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
            "title": path.rsplit("/", 1)[-1],
            "source_ref": path,
            "url": None,
            "estimated_minutes": 15 if is_adr else 20,
            "priority": "required" if is_adr else "hands_on",
        }
        if len(picked) >= _MAX_TEAM:
            break

    resources = list(picked.values())
    for r in resources:  # dormant_days from latest commit of the file
        commits = await client.list_commits(owner, repo, path=r["source_ref"], sha=request.branch, per_page=1)
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


# フロントの resourceKindSchema と一致させる許可 kind。LLM が想定外の値（例: priority の "hands_on"）を
# kind に混入させても保存しないよう、許可外は "docs" に丸める（フロントの parse 失敗→500 を防ぐ）。
_VALID_KINDS = frozenset({"adr", "video", "pr_comment", "wiki", "docs", "book", "article", "code"})


def _code_resources(steps: list[dict], code_files: list[str]) -> list[dict]:
    """Map Gemini code-learning steps to Section A (code) resources; fall back to listing files when empty."""
    valid = set(code_files)
    out: list[dict] = []
    seen: set[str] = set()
    for s in steps:
        sr = s.get("source_ref")
        if not isinstance(sr, str) or sr not in valid or sr in seen:
            continue
        seen.add(sr)
        out.append(
            {
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": str(s.get("title") or sr.rsplit("/", 1)[-1]),
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
                "title": sr.rsplit("/", 1)[-1],
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


async def _stack_terms(session: AsyncSession, request: LearningPlanGenerationRequest, *, limit: int = 10) -> list[str]:
    """Tech terms (languages + categories) from the project's tech_stack — Section B source (issue 068)."""
    owner, _, repo = request.repo_full_name.partition("/")
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


async def process(request: LearningPlanGenerationRequest, ctx: PipelineContext) -> LearningPlanGenerationResult:
    """Generate the plan's resources + ordered steps (team-first)."""
    if ctx.session is None:
        raise RuntimeError("learning_plan_generation pipeline requires a DB session in the pipeline context")
    session = ctx.session
    now = datetime.now(UTC)
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

    # 学習プランを 2 セクションで構成する（issue 068）:
    #  A. code  — このリポジトリのコードを理解する具体ステップ（機能の代表ファイル + Gemini の説明）
    #  B. stack — 検出した技術スタックの一般学習リソース（外部 URL + 説明）
    feature = None
    if plan.feature_id is not None:
        feature = (
            await session.execute(select(Feature).where(col(Feature.id) == plan.feature_id))
        ).scalar_one_or_none()

    # Section A: 学習対象のコードファイル（機能なら代表ファイル、概念スコープなら concept マッチ）。
    if feature is not None:
        code_files = await _feature_file_paths(session, feature.id)
        code_name, code_desc = feature.name, feature.description
    else:
        token = await _mint_installation_token(request.github)
        client = GitHubGitClient(access_token=token)
        try:
            code_files = [r["source_ref"] for r in await _internal_assets(client, request, now) if r.get("source_ref")]
        finally:
            await client.aclose()
        code_name = request.gap_concepts[0] if request.gap_concepts else "コード理解"
        code_desc = ""
    try:
        code_steps = await gemini_stack_service.generate_code_learning_steps(code_name, code_desc, code_files)
    except ValueError:
        logger.warning("Gemini code-learning unavailable; listing files without explanations")
        code_steps = []
    code = _code_resources(code_steps, code_files)

    # Section B: 技術スタックの一般学習リソース。
    try:
        terms = await _stack_terms(session, request)
        stack = _stack_resources(await gemini_stack_service.generate_external_resources(terms))
    except ValueError:
        logger.warning("Gemini stack-learning unavailable; code section only")
        stack = []

    # A（code）→ B（stack）の順。各セクション内は priority 順。
    ordered = sorted(code, key=lambda r: _PRIORITY_RANK.get(r["priority"], 9)) + sorted(
        stack, key=lambda r: _PRIORITY_RANK.get(r["priority"], 9)
    )

    total_minutes = 0
    for order, r in enumerate(ordered):
        resource = LearningResource(
            project_id=plan.project_id,
            origin=r["origin"],
            section=r["section"],
            kind=r["kind"],
            title=r["title"],
            summary=r["summary"],
            source_ref=r["source_ref"],
            url=r["url"],
            estimated_minutes=r["estimated_minutes"],
            priority=r["priority"],
            dormant_days=r["dormant_days"],
        )
        session.add(resource)
        await session.flush()
        session.add(LearningStep(plan_id=plan_id, order=order, completed=False, resource_id=resource.id))
        total_minutes += r["estimated_minutes"] or 0

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
    return _result(request, step_count=len(ordered), team=len(code), external=len(stack))


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
