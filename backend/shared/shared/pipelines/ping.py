"""``ping`` pipeline — minimal health probe. Returns ``pong``."""

from shared.enums import JobType, ResultStatus
from shared.pipelines.context import PipelineContext
from shared.schemas.job import PingRequest, PingResult


async def process(request: PingRequest, ctx: PipelineContext) -> PingResult:
    """Return a minimal ``pong`` result."""
    del ctx  # ping needs no shared resources
    return PingResult(
        job_id=request.job_id,
        job_type=JobType.PING,
        status=ResultStatus.COMPLETED,
        pong=True,
    )
