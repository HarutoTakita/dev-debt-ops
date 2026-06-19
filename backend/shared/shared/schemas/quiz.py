"""quiz-generation / quiz-grading pipeline request / result schemas (issue 034).

``api`` enqueues the requests; ``service`` runs Gemini (generation / semantic grading) and writes
``quiz_sessions`` / ``quiz_results``. Method B: only an ``installation_id`` crosses the queue.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class QuizGenerationRequest(JobRequestBase):
    """Queue payload to generate quiz questions for one file."""

    session_id: str
    project_id: str
    file_path: str
    repo_full_name: str = ""
    branch: str = "main"
    github: GitHubRef
    requested_by: str


class QuizGenerationResult(JobResultBase):
    """Pipeline result (summary; questions written to quiz_sessions)."""

    session_id: str
    question_count: int = 0
    agent_trace: list[str] = Field(default_factory=list)


class QuizGradingRequest(JobRequestBase):
    """Queue payload to grade one submitted quiz session."""

    session_id: str
    project_id: str
    github: GitHubRef
    requested_by: str


class QuizGradingResult(JobResultBase):
    """Pipeline result (summary; understood/gap written to quiz_results)."""

    session_id: str
    score: float = 0.0
    kc_before: float = 0.0
    kc_after: float = 0.0
    agent_trace: list[str] = Field(default_factory=list)
