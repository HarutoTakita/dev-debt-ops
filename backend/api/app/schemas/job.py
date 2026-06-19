import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shared.enums import JobStatus, JobType


class JobEnqueuedOut(BaseModel):
    """``202 Accepted`` body returned when a job is enqueued (e.g. analyze-stack)."""

    job_id: uuid.UUID = Field(..., description="Id of the created job; poll GET /jobs/{job_id}.")
    status: JobStatus = Field(..., description="Lifecycle state at enqueue time (QUEUED).")


class JobRead(BaseModel):
    """Job state as exposed to the frontend poller (``GET /api/v1/jobs/{id}``).

    For ``stack_analysis`` jobs the endpoint additionally surfaces ``agent_trace`` (lifted
    from ``Job.result_data``, which the service wrote) and ``tech_stack`` (the persisted
    ``TechStack`` row), so the progress UI and final badges can read one response.
    """

    id: uuid.UUID = Field(..., description="Job identifier.")
    job_type: JobType = Field(..., description="Pipeline kind (echo / ping / stack_analysis).")
    status: JobStatus = Field(..., description="Lifecycle state; poll until COMPLETED / FAILED.")
    result_data: dict | None = Field(default=None, description="Pipeline result (camelCase keys); null until done.")
    error: str | None = Field(default=None, description="Error summary when status is FAILED.")
    agent_trace: list[str] = Field(default_factory=list, description="Human-traceable agent steps (stack_analysis).")
    tech_stack: dict | None = Field(default=None, description="Persisted TechStack when a stack_analysis job is done.")
    created_at: datetime = Field(..., description="When the job was enqueued.")
    started_at: datetime | None = Field(default=None, description="When the service began processing.")
    completed_at: datetime | None = Field(default=None, description="When the job reached COMPLETED / FAILED.")

    model_config = ConfigDict(from_attributes=True)
