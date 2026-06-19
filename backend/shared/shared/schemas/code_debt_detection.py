"""code-debt-detection pipeline request / result schemas (issue 028).

``CodeDebtDetectionRequest`` is what ``api`` enqueues (``POST .../detect-debts``) and ``service``
validates from the Cloud Tasks body; ``CodeDebtDetectionResult`` is the summary
``service.pipelines.code_debt_detection.process`` returns and the worker writes into
``Job.result_data`` (camelCase, ``by_alias=True``). The detailed findings live in the
``code_debts`` table — only counts travel back in ``result_data`` (cf. issue 018's ``agent_trace``).

GitHub access follows method B: only an ``installation_id`` crosses the queue (reusing
``GitHubRef`` from ``stack_analysis``), and ``service`` mints the token from Secret Manager.
``run_id`` is NOT carried — ``service`` creates/reuses the ``analysis_run`` (it has the commit
sha) keyed by ``job_id`` for idempotency.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class CodeDebtDetectionRequest(JobRequestBase):
    """Queue payload for one repository code-debt detection run."""

    owner: str
    repo: str
    branch: str = "main"
    github: GitHubRef
    requested_by: str  # current_user.id (audit only)
    project_id: str  # AnalysisRun.project_id scope (1 project = 1 repo)


class CodeDebtDetectionResult(JobResultBase):
    """Pipeline result written into ``Job.result_data`` (summary only; rows in ``code_debts``)."""

    project_id: str
    run_id: str
    commit_sha: str = ""
    detected: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
