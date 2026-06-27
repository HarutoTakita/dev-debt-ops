"""repayment-pr-generation pipeline request / result schemas (issue 033).

``api`` enqueues ``RepaymentPrGenerationRequest`` (``POST .../debts/{debt_id}/repayment-pr``);
``service`` generates a Gemini refactor and opens a GitHub PR, returning the summary the worker
writes into ``Job.result_data``. Method B: only an ``installation_id`` crosses the queue.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class RepaymentPrGenerationRequest(JobRequestBase):
    """Queue payload for generating one repayment PR for a code debt."""

    debt_id: str
    owner: str
    repo: str
    branch: str = "main"  # PR base branch
    github: GitHubRef
    requested_by: str  # current_user.id (audit only)


class RepaymentPrGenerationResult(JobResultBase):
    """Pipeline result written into ``Job.result_data`` (PR refs + trace)."""

    debt_id: str
    pr_number: int | None = None
    pr_url: str | None = None
    branch: str | None = None  # head branch created
    trace: list[str] = Field(default_factory=list)
