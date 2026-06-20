"""learning-plan-generation pipeline (issue 035) — 3 stages.

1. internal_asset_search: scan the repo tree for ADRs and concept-matching code via ``GitHubGitClient``
   (method B token), compute ``dormant_days`` from the latest commit age → ``origin="team"`` resources.
2. external_resource_search: ask Gemini for external docs/books/articles → ``origin="external"`` resources
   (https URLs only).
3. plan_generator: team assets first (issue 012 §5.4), then external, ordered by priority; build
   ``learning_resources`` + ``learning_steps`` and sum ``estimated_total_minutes``.

``shared.worker.run_task`` owns the Job lifecycle. Idempotent: if the plan already has steps, skip
(the whole build commits once, so a failed run leaves no partial steps).
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlmodel import col

from service import config
from service.services import gemini_stack_service
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import LearningPlan, LearningResource, LearningStep
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
    blobs = [t.path for t in tree if t.type == "blob"]
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


def _external_resources(raw: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in raw:
        url = item.get("url")
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
            continue  # validate URL (scheme); drop invalid
        out.append(
            {
                "origin": "external",
                "kind": item.get("kind") or "docs",
                "title": str(item.get("title") or "External resource"),
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

    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    try:
        team = await _internal_assets(client, request, now)
    finally:
        await client.aclose()
    try:
        external = _external_resources(await gemini_stack_service.generate_external_resources(request.gap_concepts))
    except ValueError:
        logger.warning("Gemini external-resource search unavailable; team assets only")
        external = []

    # team first, then external; within each, by priority rank.
    ordered = sorted(team, key=lambda r: _PRIORITY_RANK.get(r["priority"], 9)) + sorted(
        external, key=lambda r: _PRIORITY_RANK.get(r["priority"], 9)
    )

    total_minutes = 0
    for order, r in enumerate(ordered):
        resource = LearningResource(
            project_id=plan.project_id,
            origin=r["origin"],
            kind=r["kind"],
            title=r["title"],
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
    await session.commit()

    logger.info(
        "learning_plan_generation: %s steps (team=%s ext=%s) for plan %s",
        len(ordered),
        len(team),
        len(external),
        request.plan_id,
    )
    return _result(request, step_count=len(ordered), team=len(team), external=len(external))


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
