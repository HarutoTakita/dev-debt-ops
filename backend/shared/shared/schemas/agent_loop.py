"""agent-loop pipeline request / result schemas (issue 036).

``api`` enqueues ``AgentLoopRequest`` (``POST .../agents/{kind}/run``); ``service`` binds the
detection domains (028-034) into a 5-stage pipeline + first-person narrative and writes the
``agent_*`` / ``narrative_*`` rows. Method B: only an ``installation_id`` crosses the queue.
``code_debt_loop`` and ``knowledge_debt_loop`` share one ``process`` (branch on ``kind``).
"""

from typing import Literal

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class AgentLoopRequest(JobRequestBase):
    """Queue payload to run one Twin-Agent loop for a project."""

    project_id: str
    owner: str
    repo: str
    branch: str = "main"
    github: GitHubRef
    kind: Literal["code_debt", "knowledge_debt"]
    requested_by: str


class AgentLoopResult(JobResultBase):
    """Pipeline result (ids + summary; rows written to agent_* / narrative_* tables)."""

    kind: str
    activity_id: str
    pipeline_id: str
    step_count: int = 0
    trace: list[str] = Field(default_factory=list)
