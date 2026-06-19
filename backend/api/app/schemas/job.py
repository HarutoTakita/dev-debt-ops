import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shared.enums import JobStatus, JobType


class JobRead(BaseModel):
    """Job state as exposed to the frontend poller (``GET /api/v1/jobs/{id}``)."""

    id: uuid.UUID = Field(..., description="Job identifier.")
    job_type: JobType = Field(..., description="Pipeline kind (echo / ping / stack_analysis).")
    status: JobStatus = Field(..., description="Lifecycle state; poll until COMPLETED / FAILED.")
    result_data: dict | None = Field(default=None, description="Pipeline result (camelCase keys); null until done.")
    error: str | None = Field(default=None, description="Error summary when status is FAILED.")
    created_at: datetime = Field(..., description="When the job was enqueued.")
    started_at: datetime | None = Field(default=None, description="When the service began processing.")
    completed_at: datetime | None = Field(default=None, description="When the job reached COMPLETED / FAILED.")

    model_config = ConfigDict(from_attributes=True)
