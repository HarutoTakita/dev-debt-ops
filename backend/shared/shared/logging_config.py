"""Structured (JSON) logging + request-context correlation (issue 302).

Cloud Run automatically ships stdout to Cloud Logging. Emitting each record as a JSON object lets
Cloud Logging parse it into ``jsonPayload`` with a real ``severity`` (so DEBUG/INFO/WARNING/ERROR are
filterable) and, when a ``logging.googleapis.com/trace`` field is present, group logs by request and
correlate with Cloud Trace. No SDK or network calls — just JSON on stdout (the Cloud Run-native path).

Usage (both api and service call this at startup):

    from shared.logging_config import configure_logging, RequestContextMiddleware
    configure_logging()
    app.add_middleware(RequestContextMiddleware)

Set ``LOG_FORMAT=text`` for a human-readable local format; the default is ``json`` (always structured).
``LOG_LEVEL`` (default ``INFO``) controls the root level.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

# Per-request correlation, set by RequestContextMiddleware and read by the formatter.
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace: ContextVar[str | None] = ContextVar("trace", default=None)

# Standard LogRecord attributes — anything else on the record is treated as a structured "extra".
_RESERVED = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
}


class StructuredFormatter(logging.Formatter):
    """Render a ``LogRecord`` as a single Cloud Logging-friendly JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize the record to a JSON string with severity, message, trace and extras."""
        entry: dict[str, Any] = {
            "severity": record.levelname,  # Cloud Logging maps DEBUG/INFO/WARNING/ERROR/CRITICAL
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "logger": record.name,
            "module": record.module,
        }
        request_id = _request_id.get()
        if request_id:
            entry["request_id"] = request_id
        trace = _trace.get()
        if trace:
            entry["logging.googleapis.com/trace"] = trace
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        # Structured extras passed via logger.info(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(*, level: str | None = None) -> None:
    """Install the root log handler. JSON by default (``LOG_FORMAT``); human-readable when ``text``.

    Also routes uvicorn/gunicorn loggers through the root handler so their records get the same
    format instead of uvicorn's plain default.
    """
    resolved_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    fmt = os.environ.get("LOG_FORMAT", "json").lower()

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    else:
        handler.setFormatter(StructuredFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(resolved_level)

    # Let server loggers propagate to the root handler (avoid duplicate/plain lines).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error", "gunicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def _extract_trace(trace_header: str, project_id: str) -> str | None:
    """Build the ``logging.googleapis.com/trace`` resource from an ``X-Cloud-Trace-Context`` header."""
    trace_id = trace_header.split("/", 1)[0].split(";", 1)[0].strip()
    return f"projects/{project_id}/traces/{trace_id}" if trace_id and project_id else None


class RequestContextMiddleware:
    """Pure-ASGI middleware: bind a request id + Cloud Trace id for the duration of each request.

    Pure ASGI (not ``BaseHTTPMiddleware``) so the ``ContextVar``s reliably propagate into the endpoint
    and any logging it does. Echoes the id back as the ``X-Request-ID`` response header.
    """

    def __init__(self, app: Any, *, project_id: str | None = None) -> None:
        self.app = app
        self.project_id = project_id if project_id is not None else os.environ.get("GOOGLE_CLOUD_PROJECT", "")

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """Bind request-id/trace context vars for the request and echo ``X-Request-ID``."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        rid_header = headers.get(b"x-request-id")
        request_id = rid_header.decode() if rid_header else uuid4().hex

        trace_value: str | None = None
        trace_header = headers.get(b"x-cloud-trace-context")
        if trace_header:
            trace_value = _extract_trace(trace_header.decode(), self.project_id)

        rid_token = _request_id.set(request_id)
        trace_token = _trace.set(trace_value)

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id.reset(rid_token)
            _trace.reset(trace_token)
