"""Health probes (issue 301).

Two endpoints, following the Kubernetes / Cloud Run split:

- ``GET /health`` — **liveness**: is the process up and serving? Intentionally dependency-free and
  instant so a slow/broken database never causes the orchestrator to kill a healthy process.
- ``GET /health/ready`` — **readiness**: are the dependencies this replica needs actually usable?
  Runs a real ``SELECT 1`` against the database and reports process memory + uptime. Returns
  ``503`` when a critical dependency (the DB) is unreachable so the load balancer can drain traffic.
"""

import time

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.db import engine

router = APIRouter()

# Process start (monotonic) — used to report uptime on the readiness probe.
_STARTED = time.monotonic()
_VERSION = "0.1.0"


class HealthResponse(BaseModel):
    """Liveness probe response envelope."""

    status: str = Field(..., description="Service status", examples=["ok"])


class DependencyCheck(BaseModel):
    """Result of probing one external dependency."""

    status: str = Field(..., description="'ok' or 'error'", examples=["ok"])
    latency_ms: float | None = Field(default=None, description="Round-trip latency of the check, in ms.")
    detail: str | None = Field(default=None, description="Error detail when status is 'error'.")


class MemoryCheck(BaseModel):
    """Process memory usage (resident set size)."""

    status: str = Field(..., description="'ok' when RSS could be read, else 'unknown'.")
    rss_mb: float | None = Field(default=None, description="Resident set size in MiB.")


class ReadinessResponse(BaseModel):
    """Deep readiness response: overall status plus per-check details."""

    status: str = Field(..., description="'ok' when all critical checks pass, else 'degraded'.")
    version: str = Field(..., description="Service version.")
    uptime_seconds: float = Field(..., description="Seconds since the process started.")
    database: DependencyCheck
    memory: MemoryCheck


def _rss_mb() -> float | None:
    """Best-effort current resident set size in MiB (Linux ``/proc``; ``resource`` fallback)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)  # value is in kB
    except (OSError, ValueError, IndexError):
        pass
    try:
        import resource
        import sys

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # kB on Linux, bytes on macOS
        return round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    except (ValueError, OSError):
        return None


@router.get(
    "/health",
    summary="Liveness check",
    response_description="Service is accepting traffic.",
    response_model=HealthResponse,
    tags=["Health"],
)
async def health_check() -> HealthResponse:
    """Liveness probe: the process is alive and serving requests.

    Dependency-free and instant by design — it does **not** touch the database. Use
    ``/health/ready`` for a deep readiness check.
    """
    return HealthResponse(status="ok")


@router.get(
    "/health/ready",
    summary="Readiness check",
    response_description="Dependency and resource health for this replica.",
    response_model=ReadinessResponse,
    tags=["Health"],
    responses={503: {"model": ReadinessResponse, "description": "A critical dependency is unavailable."}},
)
async def readiness_check(response: Response) -> ReadinessResponse:
    """Readiness probe: verify the database is reachable and report memory + uptime.

    Runs ``SELECT 1`` and measures its latency. If the database check fails the endpoint returns
    ``503`` (overall status ``degraded``) so the orchestrator/LB can stop routing traffic here.
    """
    started = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        database = DependencyCheck(status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 2))
    except Exception as exc:  # any driver/connection error → not ready
        database = DependencyCheck(
            status="error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail=type(exc).__name__,
        )

    rss = _rss_mb()
    memory = MemoryCheck(status="ok" if rss is not None else "unknown", rss_mb=rss)

    overall_ok = database.status == "ok"
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ok" if overall_ok else "degraded",
        version=_VERSION,
        uptime_seconds=round(time.monotonic() - _STARTED, 1),
        database=database,
        memory=memory,
    )
