"""Domain exception hierarchy.

Route handlers and services raise these instead of `HTTPException`. A single
exception handler registered in `main.py` translates them to JSON responses
with the matching status code, so status codes live with the error semantics,
not sprinkled through the routes.

`HTTPException` is still valid — fastapi-users raises it internally and the
default FastAPI handler keeps working for those.
"""


class AppError(Exception):
    """Base class for domain errors that translate to HTTP responses.

    Subclasses customise two class attributes: `status_code` (the HTTP status code written
    into the response) and `default_detail` (the fallback message when no explicit detail is
    supplied). The exception handler registered in `main.py` reads these attributes and builds
    the JSON error body — keeping status-code semantics co-located with the error class rather
    than scattered across route handlers.
    """

    status_code: int = 500
    default_detail: str = "Internal error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class BadRequestError(AppError):
    """Raised when the client sends a malformed or invalid request."""

    status_code = 400
    default_detail = "Bad request"


class PermissionDeniedError(AppError):
    """Raised when the caller lacks permission for the requested action."""

    status_code = 403
    default_detail = "Permission denied"


class NotFoundError(AppError):
    """Raised when the requested resource does not exist or is not visible to the caller."""

    status_code = 404
    default_detail = "Resource not found"


class ConflictError(AppError):
    """Raised when the request conflicts with current resource state (e.g. unique constraint)."""

    status_code = 409
    default_detail = "Conflict"


class PayloadTooLargeError(AppError):
    """Raised when the request body exceeds allowed size."""

    status_code = 413
    default_detail = "Payload too large"


class UnsupportedMediaTypeError(AppError):
    """Raised when the request's content-type is not supported."""

    status_code = 415
    default_detail = "Unsupported media type"


class UnprocessableError(AppError):
    """Raised when the request is well-formed but semantically invalid."""

    status_code = 422
    default_detail = "Unprocessable entity"
