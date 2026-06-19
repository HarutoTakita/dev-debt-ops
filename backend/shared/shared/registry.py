"""Pipeline registry — maps a pipeline name to ``(request_model, result_model, process)``.

Ported from ``app_ref/services/worker/worker/registry.py``. The key is the pipeline
name carried in the Cloud Tasks path (``/tasks/{pipeline}``) — equal to the ``JobType``
value (``echo`` / ``ping``). Both api's mock-worker and service's task handler resolve
pipelines through this dict.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from shared.enums import JobType
from shared.pipelines import echo, ping
from shared.pipelines.context import PipelineContext
from shared.schemas.job import EchoRequest, EchoResult, JobRequestBase, JobResultBase, PingRequest, PingResult

# (request_model, result_model, process_fn)
Pipeline = tuple[type[JobRequestBase], type[JobResultBase], Callable[[Any, PipelineContext], Awaitable[JobResultBase]]]

PIPELINES: dict[str, Pipeline] = {
    JobType.ECHO.value: (EchoRequest, EchoResult, echo.process),
    JobType.PING.value: (PingRequest, PingResult, ping.process),
}
