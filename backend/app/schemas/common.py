from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error envelope returned by `AppError` subclasses via the handler in `main.py`."""

    detail: str = Field(..., description="Human-readable error message")
