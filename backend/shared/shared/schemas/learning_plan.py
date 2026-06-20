"""learning-plan-generation pipeline request / result schemas (issue 035).

``api`` creates the ``learning_plans`` row and enqueues this request; ``service`` runs the 3-stage
generation (internal asset search → external resources → plan) and fills steps/resources.
Method B: only an ``installation_id`` crosses the queue.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class LearningPlanGenerationRequest(JobRequestBase):
    """Queue payload to generate a learning plan for a set of gap concepts."""

    plan_id: str
    project_id: str
    gap_concepts: list[str] = Field(default_factory=list)  # normalized Concept.id list
    quiz_session_id: str | None = None
    repo_full_name: str = ""
    branch: str = "main"
    github: GitHubRef
    requested_by: str


class LearningPlanGenerationResult(JobResultBase):
    """Pipeline result (summary; resources/steps written to learning_* tables)."""

    plan_id: str
    step_count: int = 0
    team_count: int = 0
    external_count: int = 0
