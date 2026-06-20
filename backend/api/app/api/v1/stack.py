"""Tech-stack analysis API.

``POST .../analyze-stack`` is async (issue 018): it resolves the caller's GitHub App
installation id, enqueues a ``stack_analysis`` Job via Cloud Tasks, and returns ``202``
immediately — the ADK agent runs in the ``service`` container, off the api request path.
The frontend polls ``GET /jobs/{id}``. ``GET .../stack`` reads the persisted ``TechStack``
(404 = not yet analysed).

``TechStack`` is keyed globally on ``(owner, repo)``, so both routes verify the caller's
GitHub App installation actually manages ``owner/repo`` before reading or triggering analysis
(issue-039). Otherwise any authenticated user could read another tenant's (possibly private)
cached analysis by guessing ``owner/repo``.
"""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select as sa_select

from app.api.deps import CurrentUser, SASessionDep, SessionDep, get_github_app_service
from app.api.v1.github import InstallationIdDep
from app.schemas.job import JobEnqueuedOut
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.github_app import GitHubAppService
from app.services.job_orchestrator import enqueue_job
from shared.enums import JobType
from shared.models import TechStack
from shared.queue import BlobClient, TaskDispatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["Stack"])

GitHubAppDep = Annotated[GitHubAppService, Depends(get_github_app_service)]


async def verify_repo_access(github_app: GitHubAppService, installation_id: int, owner: str, repo: str) -> None:
    """Ensure the caller's installation manages ``owner/repo``; raise 404 otherwise.

    Compares the repo's managing installation with the caller's resolved installation. A
    mismatch (or a repo the App can't see) is reported as 404 — we don't leak whether the
    repo exists or has been analysed by another tenant.
    """
    try:
        repo_installation = await github_app.get_installation_for_repo(owner, repo)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Repository not found or not accessible") from exc
        raise HTTPException(status_code=502, detail="GitHub API error") from exc
    if repo_installation != installation_id:
        raise HTTPException(status_code=404, detail="Repository not found or not accessible")


# ---------------------------------------------------------------------------
# Response models (GET .../stack — interface unchanged)
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
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="テックスタック解析を非同期ジョブとして enqueue する",
)
async def analyze_stack(
    owner: str,
    repo: str,
    installation_id: InstallationIdDep,
    github_app: GitHubAppDep,
    current_user: CurrentUser,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
    branch: str = "main",
) -> JobEnqueuedOut:
    """Enqueue a ``stack_analysis`` job and return ``202`` with the job id.

    The heavy ADK agent (list_key_files → read_file → classify_stack → save_stack) runs in
    the ``service`` container off the request path; method B keeps the GitHub secret off the
    queue (only ``installation_id`` is carried, the service mints the token). The frontend
    polls ``GET /jobs/{job_id}`` for progress (``agent_trace``) and the final ``tech_stack``.
    """
    await verify_repo_access(github_app, installation_id, owner, repo)
    payload = {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "requested_by": str(current_user.id),  # audit only (service reads created_by from the Job)
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=JobType.STACK_ANALYSIS,
        payload=payload,
        created_by=current_user.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)


@router.get(
    "/repositories/{owner}/{repo}/stack",
    response_model=TechStackOut,
    summary="保存済みのテックスタック解析結果を返す",
)
async def get_stack(
    owner: str,
    repo: str,
    installation_id: InstallationIdDep,
    github_app: GitHubAppDep,
    session: SASessionDep,
) -> TechStackOut:
    """Return the most recent cached tech-stack analysis. 404 if not yet analysed.

    Requires authentication (via ``InstallationIdDep``) and verifies the caller's installation
    manages ``owner/repo`` (issue-039) before reading the global ``(owner, repo)`` cache.
    """
    await verify_repo_access(github_app, installation_id, owner, repo)
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
