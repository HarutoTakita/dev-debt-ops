from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class HealthResponse(BaseModel):
    """Liveness probe response envelope."""

    status: str = Field(..., description="Service status", examples=["ok"])


@router.get(
    "/health",
    summary="Liveness check",
    response_description="Service is accepting traffic.",
    response_model=HealthResponse,
    tags=["Health"],
)
async def health_check() -> HealthResponse:
    """Check that the service process is alive and accepting requests.

    This is a Kubernetes-style liveness probe only — it does not check the
    database connection or any external dependencies. Use a dedicated readiness
    probe for deeper dependency checks.
    """
    return HealthResponse(status="ok")
