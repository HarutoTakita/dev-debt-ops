"""Job request / result payload schemas (camelCase across the queue boundary).

Request schemas are what ``api`` builds and ``service`` validates from the Cloud Tasks
body; result schemas are what a pipeline ``process`` returns and ``service`` writes into
``Job.result_data``. ``echo`` / ``ping`` are the issue-016 plumbing probes.
"""

from shared.enums import JobType, ResultStatus
from shared.schemas.base import PipelineError, PipelineTiming, SharedBaseModel


class JobRequestBase(SharedBaseModel):
    """Common envelope for every pipeline request sent over the queue."""

    job_id: str
    job_type: JobType
    schema_version: str = "1.0"


class JobResultBase(SharedBaseModel):
    """Common envelope for every pipeline result written back to ``Job.result_data``."""

    job_id: str
    job_type: JobType
    status: ResultStatus
    error: PipelineError | None = None
    timing: PipelineTiming | None = None


class EchoRequest(JobRequestBase):
    """Echo probe request — returns its ``message`` unchanged."""

    message: str


class EchoResult(JobResultBase):
    """Echo probe result."""

    echoed: str | None = None


class PingRequest(JobRequestBase):
    """Ping probe request — minimal, no inputs."""


class PingResult(JobResultBase):
    """Ping probe result."""

    pong: bool = True
