"""Stack-analysis pipeline request / result schemas (issue 018).

``StackAnalysisRequest`` is what ``api`` enqueues and ``service`` validates from the Cloud
Tasks body; ``StackAnalysisResult`` is what ``service.pipelines.stack_analysis.process``
returns and the worker writes into ``Job.result_data`` (camelCase, ``by_alias=True``).

``TechItem`` / ``TechCategories`` are promoted here from api's old ``TechItemOut`` /
``TechCategoriesOut`` so both api (response) and service (pipeline) share one shape. The
GitHub token is NOT carried in the payload (method B, see issue 018): only an
``installation_id`` travels over the queue, and ``service`` mints the token from Secret
Manager. ``access_token`` is kept optional purely so method A stays expressible.
"""

from typing import Literal

from pydantic import Field, SecretStr

from shared.schemas.base import SharedBaseModel
from shared.schemas.job import JobRequestBase, JobResultBase

Confidence = Literal["high", "medium", "low"]


class TechItem(SharedBaseModel):
    """A single detected technology with a confidence level."""

    name: str
    confidence: Confidence


class TechCategories(SharedBaseModel):
    """Detected technologies grouped into the nine analysis categories."""

    frameworks: list[TechItem] = Field(default_factory=list)
    databases: list[TechItem] = Field(default_factory=list)
    auth: list[TechItem] = Field(default_factory=list)
    container: list[TechItem] = Field(default_factory=list)
    infra: list[TechItem] = Field(default_factory=list)
    cicd: list[TechItem] = Field(default_factory=list)
    monitoring: list[TechItem] = Field(default_factory=list)
    testing: list[TechItem] = Field(default_factory=list)
    other: list[TechItem] = Field(default_factory=list)


class GitHubRef(SharedBaseModel):
    """How ``service`` reaches GitHub for one analysis.

    Method B (recommended): carry only ``installation_id`` — ``service`` mints a short-lived
    installation token from the Secret Manager-backed GitHub App private key, so no secret
    ever lands on the queue / GCS. ``access_token`` exists only for method-A compatibility
    and is left unset under method B.
    """

    installation_id: int
    access_token: SecretStr | None = None


class StackAnalysisRequest(JobRequestBase):
    """Queue payload for one repository tech-stack analysis."""

    owner: str
    repo: str
    branch: str = "main"
    github: GitHubRef
    requested_by: str  # current_user.id (audit only)


class StackAnalysisResult(JobResultBase):
    """Pipeline result written into ``Job.result_data`` (no Pub/Sub, no api callback)."""

    owner: str
    repo: str
    branch: str = "main"
    languages: list[TechItem] = Field(default_factory=list)
    categories: TechCategories = Field(default_factory=TechCategories)
    agent_trace: list[str] = Field(default_factory=list)
