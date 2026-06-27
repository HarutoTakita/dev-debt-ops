"""Agentic-analysis pipeline request / result schemas (issue 069).

The ``agentic_analysis`` pipeline runs the ADK Twin Agent (coordinator + knowledge/code
specialists, wrapped in a ``LoopAgent``) over a repository. Like ``stack_analysis`` it carries
only a method-B ``GitHubRef`` (``installation_id``) over the queue — no secret travels on the
queue / GCS. The result records the agent trace + finding counts into ``Job.result_data``.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class AgenticAnalysisRequest(JobRequestBase):
    """Queue payload for one agentic (Twin Agent) repository analysis."""

    owner: str
    repo: str
    branch: str = "main"
    project_id: str
    github: GitHubRef
    requested_by: str  # current_user.id (audit only)


class AgenticAnalysisResult(JobResultBase):
    """Twin Agent run result written into ``Job.result_data`` (no Pub/Sub, no api callback)."""

    owner: str
    repo: str
    branch: str
    summary: str = ""
    agent_trace: list[str] = Field(default_factory=list)
