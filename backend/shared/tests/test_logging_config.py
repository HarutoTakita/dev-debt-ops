"""issue 302: structured JSON logging + request/trace correlation."""

import json
import logging
import sys

from shared.logging_config import StructuredFormatter, _extract_trace, _request_id, _trace


def _record(level: int, msg: str, args=None, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord("mylogger", level, __file__, 10, msg, args, exc_info)


def test_formatter_emits_json_with_severity_and_message() -> None:
    out = json.loads(StructuredFormatter().format(_record(logging.WARNING, "hello %s", ("world",))))
    assert out["severity"] == "WARNING"  # Cloud Logging severity
    assert out["message"] == "hello world"
    assert out["logger"] == "mylogger"
    assert "time" in out


def test_formatter_includes_request_context_and_extra() -> None:
    rid = _request_id.set("req-123")
    tr = _trace.set("projects/p/traces/abc")
    try:
        rec = _record(logging.INFO, "processing")
        rec.job_type = "agentic_analysis"  # a structured extra (logger.info(..., extra=...))
        out = json.loads(StructuredFormatter().format(rec))
        assert out["request_id"] == "req-123"
        assert out["logging.googleapis.com/trace"] == "projects/p/traces/abc"
        assert out["job_type"] == "agentic_analysis"
    finally:
        _request_id.reset(rid)
        _trace.reset(tr)


def test_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        rec = _record(logging.ERROR, "failed", exc_info=sys.exc_info())
    out = json.loads(StructuredFormatter().format(rec))
    assert "ValueError" in out["exception"]


def test_extract_trace_from_cloud_run_header() -> None:
    assert _extract_trace("abc123/456;o=1", "myproj") == "projects/myproj/traces/abc123"
    assert _extract_trace("abc123/456", "") is None  # no project id → no trace resource
