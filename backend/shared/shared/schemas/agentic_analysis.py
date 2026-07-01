"""Agentic-analysis pipeline request / result schemas (issue 069 → 266).

The ``agentic_analysis`` pipeline runs the agent-first repository analysis: the Base Analysis Agent
produces the qualitative "元データ", then the deterministic backbone formats/enhances it into the
screen tables. Like ``stack_analysis`` it carries only a method-B ``GitHubRef`` (``installation_id``)
over the queue — no secret travels on the queue / GCS. The result records the agent trace into
``Job.result_data``.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class AgenticAnalysisRequest(JobRequestBase):
    """Queue payload for one agentic repository analysis."""

    owner: str
    repo: str
    branch: str = "main"
    project_id: str
    github: GitHubRef
    requested_by: str  # current_user.id (audit only)


class AgenticAnalysisResult(JobResultBase):
    """Agentic-analysis run result written into ``Job.result_data`` (no Pub/Sub, no api callback)."""

    owner: str
    repo: str
    branch: str
    summary: str = ""
    agent_trace: list[str] = Field(default_factory=list)
