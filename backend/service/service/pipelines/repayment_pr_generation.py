"""repayment-pr-generation pipeline (issue 033).

For one ``code_debt``: fetch the file, ask Gemini for a refactor, open a GitHub PR (branch → commit →
PR) via the write-extended ``GitHubGitClient`` (method B token), then set ``code_debts.related_pr`` /
``status="in_pr"``. ``shared.worker.run_task`` owns the Job lifecycle + ``result_data``.

Idempotent across at-least-once redelivery: if the debt is already ``in_pr`` with a ``related_pr`` the
PR is **not** re-created — the existing reference is returned (avoids duplicate GitHub side effects).
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services import gemini_stack_service
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import CodeDebt
from shared.pipelines.context import PipelineContext
from shared.schemas.repayment_pr_generation import RepaymentPrGenerationRequest, RepaymentPrGenerationResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def _load_debt(session: AsyncSession, debt_id: uuid.UUID) -> CodeDebt | None:
    return (await session.execute(select(CodeDebt).where(col(CodeDebt.id) == debt_id))).scalar_one_or_none()


def _result(
    request: RepaymentPrGenerationRequest,
    *,
    pr_number: int | None,
    pr_url: str | None,
    branch: str | None,
    trace: list[str],
) -> RepaymentPrGenerationResult:
    return RepaymentPrGenerationResult(
        job_id=request.job_id,
        job_type=JobType.REPAYMENT_PR_GENERATION,
        status=ResultStatus.COMPLETED,
        debt_id=request.debt_id,
        pr_number=pr_number,
        pr_url=pr_url,
        branch=branch,
        trace=trace,
    )


async def process(request: RepaymentPrGenerationRequest, ctx: PipelineContext) -> RepaymentPrGenerationResult:
    """Generate a refactor PR for the code debt and mark it ``in_pr``."""
    if ctx.session is None:
        raise RuntimeError("repayment_pr_generation pipeline requires a DB session in the pipeline context")
    session = ctx.session
    trace: list[str] = []

    debt = await _load_debt(session, uuid.UUID(request.debt_id))
    if debt is None:
        return _result(request, pr_number=None, pr_url=None, branch=None, trace=["debt not found"])

    # Idempotency: already has a PR → do not create another.
    if debt.status == "in_pr" and debt.related_pr:
        return _result(request, pr_number=None, pr_url=None, branch=None, trace=[f"already in_pr ({debt.related_pr})"])

    head_branch = f"rosetta/repay-{request.debt_id[:8]}"
    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    try:
        current = await client.get_file_content(request.owner, request.repo, debt.file_path, request.branch)
        refactor = await gemini_stack_service.generate_refactor(
            debt.file_path, current.content or "", debt.archaeology_notes
        )
        trace.append("generated refactor")

        base_sha = await client.get_branch_sha(request.owner, request.repo, request.branch)
        await client.create_branch(request.owner, request.repo, head_branch, base_sha)
        await client.create_or_update_file(
            request.owner,
            request.repo,
            debt.file_path,
            message=refactor["pr_title"],
            content=refactor["new_content"],
            branch=head_branch,
            sha=current.sha,
        )
        pr_number, pr_url = await client.create_pull_request(
            request.owner,
            request.repo,
            title=refactor["pr_title"],
            head=head_branch,
            base=request.branch,
            body=f"{refactor['pr_body']}\n\n---\n🤖 自動生成（返済 PR）。根拠: {debt.archaeology_notes}",
        )
        trace.append(f"opened PR #{pr_number}")
    finally:
        await client.aclose()

    debt.related_pr = f"#{pr_number}"
    debt.status = "in_pr"
    session.add(debt)
    await session.commit()

    logger.info("repayment_pr_generation: opened PR #%s for debt %s", pr_number, request.debt_id)
    return _result(request, pr_number=pr_number, pr_url=pr_url, branch=head_branch, trace=trace)
