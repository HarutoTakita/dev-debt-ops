"""Feature-clustering pipeline request / result schemas (issue 052).

``FeatureClusteringRequest`` is what ``api`` enqueues and ``service`` validates from the Cloud
Tasks body; ``FeatureClusteringResult`` is what ``service.pipelines.feature_clustering.process``
returns and the worker writes into ``Job.result_data`` (camelCase, ``by_alias=True``).

Method B: only ``installation_id`` travels over the queue (``GitHubRef``); ``service`` mints the
token from Secret Manager.
"""

from pydantic import Field

from shared.schemas.job import JobRequestBase, JobResultBase
from shared.schemas.stack_analysis import GitHubRef


class FeatureClusteringRequest(JobRequestBase):
    """Queue payload for one repository feature-clustering run."""

    owner: str
    repo: str
    branch: str = "main"
    github: GitHubRef
    project_id: str
    requested_by: str  # current_user.id (audit only)


class FeatureClusteringResult(JobResultBase):
    """Pipeline result written into ``Job.result_data``."""

    owner: str
    repo: str
    branch: str = "main"
    feature_count: int = 0
    file_count: int = 0
    trace: list[str] = Field(default_factory=list)
