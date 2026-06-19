"""Tech-stack analysis API: ADK agent scans a repo and classifies its technologies."""

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select as sa_select

from app.agent.stack_agent import run_stack_analysis
from app.api.deps import SASessionDep
from app.api.v1.github import GitHubClientDep
from app.models.tech_stack import TechStack

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["Stack"])


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
    analyzed_at: object
    languages: list[TechItemOut]
    categories: TechCategoriesOut
    agent_trace: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_out(row: TechStack, agent_trace: list[str] | None = None) -> TechStackOut:
    """Convert a TechStack DB row to the API response model."""

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
        agent_trace=agent_trace or [],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/repositories/{owner}/{repo}/analyze-stack",
    response_model=TechStackOut,
    summary="ADK エージェントでリポジトリのテックスタックを解析・保存する",
)
async def analyze_stack(
    owner: str,
    repo: str,
    client: GitHubClientDep,
    session: SASessionDep,
    branch: str = "main",
) -> TechStackOut:
    """Run the ADK Stack Analysis Agent to autonomously fetch, classify, and persist the tech stack.

    The agent calls list_key_files -> read_file (xN) -> classify_stack -> save_stack in sequence.
    The agent_trace field in the response records each tool call for observability.
    """
    try:
        trace = await run_stack_analysis(client, session, owner, repo, branch)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="GitHub API error") from e
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("Stack analysis agent failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Agent error: {e}") from e

    # Agent should have called save_stack; read the persisted result
    result = await session.execute(
        sa_select(TechStack).where(
            TechStack.owner == owner,  # ty: ignore[invalid-argument-type]
            TechStack.repo == repo,  # ty: ignore[invalid-argument-type]
        )
    )
    tech_stack = result.scalar_one_or_none()
    if not tech_stack:
        raise HTTPException(status_code=502, detail="Agent did not save the tech stack result.")
    return _row_to_out(tech_stack, trace)


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
    result = await session.execute(
        sa_select(TechStack).where(
            TechStack.owner == owner,  # ty: ignore[invalid-argument-type]
            TechStack.repo == repo,  # ty: ignore[invalid-argument-type]
        )
    )
    tech_stack = result.scalar_one_or_none()
    if not tech_stack:
        raise HTTPException(status_code=404, detail="Not yet analysed. Call POST analyze-stack first.")
    return _row_to_out(tech_stack)
