"""knowledge-debt-detection pipeline request / result schemas (issue 030).

``KnowledgeDebtDetectionRequest`` is what ``api`` enqueues (``POST .../detect-knowledge-debts``) and
``service`` validates; ``KnowledgeDebtDetectionResult`` is the summary ``process`` returns and the
worker writes into ``Job.result_data``. Findings live in ``knowledge_debts`` / ``assigned_developers``
— only counts + a short trace travel back.

Method B: only an ``installation_id`` crosses the queue (reusing ``GitHubRef``); ``service`` mints the
token and creates/reuses the ``analysis_run`` keyed by ``job_id``.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class KnowledgeDebtDetectionRequest(JobRequestBase):
    """Queue payload for one repository knowledge-debt detection run."""

    owner: str
    repo: str
    branch: str = "main"
    github: GitHubRef
    requested_by: str  # current_user.id (audit only)
    project_id: str  # AnalysisRun.project_id scope (1 project = 1 repo)


class KnowledgeDebtDetectionResult(JobResultBase):
    """Pipeline result written into ``Job.result_data`` (summary only)."""

    project_id: str
    run_id: str
    commit_sha: str = ""
    detected: int = 0
    reasons: dict[str, int] = Field(default_factory=dict)
    trace: list[str] = Field(default_factory=list)
