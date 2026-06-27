"""Origin-check middleware — CSRF defense-in-depth for cookie auth (issue-041).

State-changing requests are authenticated by the ``SameSite=Lax`` access cookie. ``Lax`` blocks
the classic cross-site form POST, but is a single line of defense. This middleware adds an
``Origin`` allow-list check on unsafe methods: a browser always sends ``Origin`` on cross-site
state-changing requests, so a mismatching ``Origin`` is rejected with 403.

A *missing* ``Origin`` is allowed (non-browser clients, same-origin navigations that omit it,
and the test client) — those still fall back to the ``SameSite`` cookie. The check is therefore
additive and does not replace ``SameSite``.
"""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _netloc(origin: str) -> str:
    """Return the ``host[:port]`` of a URL/origin (empty string if unparseable)."""
    return urlsplit(origin).netloc


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject unsafe-method requests whose ``Origin`` is neither same-origin nor the frontend."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject the request (403) when a present ``Origin`` is neither same-origin nor allow-listed."""
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin:
                allowed = {_netloc(settings.FRONTEND_ORIGIN)}
                host = request.headers.get("host")
                if host:
                    allowed.add(host)  # same-origin (scheme-agnostic)
                if _netloc(origin) not in allowed:
                    return JSONResponse(status_code=403, content={"detail": "Cross-origin request rejected"})
        return await call_next(request)
