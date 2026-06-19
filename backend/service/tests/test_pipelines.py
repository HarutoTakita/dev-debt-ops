"""Unit tests for the echo / ping pipeline process functions (no DB / HTTP)."""

from shared.enums import JobType, ResultStatus
from shared.pipelines import echo, ping
from shared.pipelines.context import PipelineContext
from shared.schemas.job import EchoRequest, PingRequest


async def test_echo_returns_message() -> None:
    result = await echo.process(EchoRequest(job_id="1", job_type=JobType.ECHO, message="hello"), PipelineContext())
    assert result.status == ResultStatus.COMPLETED
    assert result.echoed == "hello"
    assert result.job_id == "1"


async def test_ping_returns_pong() -> None:
    result = await ping.process(PingRequest(job_id="2", job_type=JobType.PING), PipelineContext())
    assert result.status == ResultStatus.COMPLETED
    assert result.pong is True
