"""kc-analysis pipeline request / result schemas (issue 029).

``KcAnalysisRequest`` is what ``api`` enqueues (``POST .../analyze-kc``) and ``service`` validates
from the Cloud Tasks body; ``KcAnalysisResult`` is the summary ``kc_analysis.process`` returns and
the worker writes into ``Job.result_data``. The detailed KC / wormhole rows live in ``file_kc`` /
``dependencies`` — only counts + a short trace travel back.

Method B: only an ``installation_id`` crosses the queue (reusing ``GitHubRef`` from stack_analysis);
``service`` mints the token and creates/reuses the ``analysis_run`` (keyed by ``job_id``).
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class KcAnalysisRequest(JobRequestBase):
    """Queue payload for one repository Knowledge-Coverage analysis run."""

    owner: str
    repo: str
    branch: str = "main"
    github: GitHubRef
    requested_by: str  # current_user.id (audit only)
    project_id: str  # AnalysisRun.project_id scope (1 project = 1 repo)


class KcAnalysisResult(JobResultBase):
    """Pipeline result written into ``Job.result_data`` (summary only; rows in file_kc / dependencies)."""

    project_id: str
    run_id: str
    commit_sha: str = ""
    file_kc_count: int = 0
    dependency_count: int = 0
    trace: list[str] = Field(default_factory=list)
