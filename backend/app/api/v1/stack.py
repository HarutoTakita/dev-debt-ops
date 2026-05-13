"""Tech-stack analysis API: scan a repo and classify its technologies with Gemini."""

import asyncio
import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import SASessionDep
from app.api.v1.github import GitHubClientDep
from app.models.base import generate_uuid7
from app.models.tech_stack import TechStack
from app.services.gemini_stack_service import analyze_tech_stack

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["Stack"])

# ---------------------------------------------------------------------------
# File-selection constants
# ---------------------------------------------------------------------------

_TARGET_FILENAMES = {
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "pom.xml",
    "build.gradle",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

_TARGET_EXTENSIONS = {".tf", ".bicep"}

_MAX_FILES = 20


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TechItemOut(BaseModel):
    """A single detected technology with confidence level."""

    name: str
    confidence: str


class TechCategoriesOut(BaseModel):
    """Technology items grouped by category."""

    frameworks: list[TechItemOut]
    databases: list[TechItemOut]
    auth: list[TechItemOut]
    container: list[TechItemOut]
    infra: list[TechItemOut]
    cicd: list[TechItemOut]
    monitoring: list[TechItemOut]
    testing: list[TechItemOut]
    other: list[TechItemOut]


class TechStackOut(BaseModel):
    """Full tech-stack analysis result for a repository."""

    owner: str
    repo: str
    analyzed_at: datetime
    languages: list[TechItemOut]
    categories: TechCategoriesOut


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _select_files(tree_items: list) -> list[str]:
    """Return paths of config files worth sending to Gemini."""
    selected: list[str] = []
    for item in tree_items:
        if item.type != "blob":
            continue
        path: str = item.path
        filename = path.rsplit("/", 1)[-1]
        ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""

        is_target = (
            filename in _TARGET_FILENAMES
            or ext in _TARGET_EXTENSIONS
            or (".github/workflows/" in path and (path.endswith(".yml") or path.endswith(".yaml")))
        )
        if is_target:
            selected.append(path)
        if len(selected) >= _MAX_FILES:
            break
    return selected


def _row_to_out(row: TechStack) -> TechStackOut:
    def _items(lst: list) -> list[TechItemOut]:
        return [TechItemOut(name=i["name"], confidence=i["confidence"]) for i in lst]

    cats = row.categories or {}
    return TechStackOut(
        owner=row.owner,
        repo=row.repo,
        analyzed_at=row.analyzed_at,
        languages=_items(row.languages or []),
        categories=TechCategoriesOut(
            frameworks=_items(cats.get("frameworks", [])),
            databases=_items(cats.get("databases", [])),
            auth=_items(cats.get("auth", [])),
            container=_items(cats.get("container", [])),
            infra=_items(cats.get("infra", [])),
            cicd=_items(cats.get("cicd", [])),
            monitoring=_items(cats.get("monitoring", [])),
            testing=_items(cats.get("testing", [])),
            other=_items(cats.get("other", [])),
        ),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/repositories/{owner}/{repo}/analyze-stack",
    response_model=TechStackOut,
    summary="リポジトリのテックスタックを Gemini で解析・保存する",
)
async def analyze_stack(
    owner: str,
    repo: str,
    client: GitHubClientDep,
    session: SASessionDep,
) -> TechStackOut:
    """Fetch key config files, analyse with Gemini, and upsert the result."""
    try:
        tree_items = await client.get_repository_tree(owner, repo)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="GitHub API error") from e

    target_paths = _select_files(tree_items)

    async def _fetch(path: str) -> tuple[str, str | None]:
        try:
            fc = await client.get_file_content(owner, repo, path)
            return path, fc.content
        except Exception:
            return path, None

    fetched = await asyncio.gather(*[_fetch(p) for p in target_paths])
    file_map = {path: content for path, content in fetched if content}

    try:
        result = await analyze_tech_stack(file_map)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("Gemini analyze_tech_stack failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}") from e

    now = datetime.now(UTC)
    new_id = generate_uuid7()

    stmt = pg_insert(TechStack).values(
        id=new_id,
        owner=owner,
        repo=repo,
        analyzed_at=now,
        languages=result.get("languages", []),
        categories=result.get("categories", {}),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_tech_stacks_owner_repo",
        set_={
            "analyzed_at": now,
            "languages": result.get("languages", []),
            "categories": result.get("categories", {}),
        },
    )
    await session.execute(stmt)
    await session.commit()

    saved = await session.execute(sa_select(TechStack).where(TechStack.owner == owner, TechStack.repo == repo))
    tech_stack = saved.scalar_one()
    return _row_to_out(tech_stack)


@router.get(
    "/repositories/{owner}/{repo}/stack",
    response_model=TechStackOut,
    summary="保存済みのテックスタック解析結果を返す",
)
async def get_stack(
    owner: str,
    repo: str,
    session: SASessionDep,
) -> TechStackOut:
    """Return the most recent cached tech-stack analysis. 404 if not yet analysed."""
    result = await session.execute(sa_select(TechStack).where(TechStack.owner == owner, TechStack.repo == repo))
    tech_stack = result.scalar_one_or_none()
    if not tech_stack:
        raise HTTPException(status_code=404, detail="Not yet analysed. Call POST analyze-stack first.")
    return _row_to_out(tech_stack)
