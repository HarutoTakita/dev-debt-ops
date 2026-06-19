"""``echo`` pipeline — end-to-end plumbing probe. Returns its input unchanged."""

from shared.enums import JobType, ResultStatus
from shared.pipelines.context import PipelineContext
from shared.schemas.job import EchoRequest, EchoResult


async def process(request: EchoRequest, ctx: PipelineContext) -> EchoResult:
    """Echo the request ``message`` back as ``echoed``."""
    del ctx  # echo needs no shared resources
    return EchoResult(
        job_id=request.job_id,
        job_type=JobType.ECHO,
        status=ResultStatus.COMPLETED,
        echoed=request.message,
    )
