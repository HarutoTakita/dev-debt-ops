import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.csrf import OriginCheckMiddleware
from app.core.db import engine
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve SPA — fall back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve the requested path, falling back to `index.html` on 404."""
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


_is_prod = settings.ENVIRONMENT == "prod"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start the in-process mock-worker (mock mode only); dispose the DB engine on shutdown.

    In production (``USE_MOCK_WORKER=false``) no background loop runs — Cloud Tasks pushes
    to the separate ``service`` container, keeping api request-driven / zero-scalable.
    """
    logger.info("Starting backend replica: %s", os.environ.get("REPLICA_ID", "single"))
    mock_worker_task: asyncio.Task[None] | None = None
    if settings.use_mock_worker():
        from app.services.mock_worker import run_mock_worker

        mock_worker_task = asyncio.create_task(run_mock_worker())
    try:
        yield
    finally:
        if mock_worker_task is not None:
            mock_worker_task.cancel()
        await engine.dispose()


tags_metadata: list[dict[str, str]] = [
    {"name": "Health", "description": "Liveness and readiness probes"},
]

app = FastAPI(
    title="DevDebtOps",
    summary="Tech Debt Twin Agent — SvelteKit + FastAPI + PostgreSQL",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if not _is_prod else None,
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    """Translate any `AppError` subclass into a JSON response with its `status_code`."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# CSRF defense-in-depth: reject unsafe-method requests with a cross-origin Origin header
# (issue-041). Additive to the SameSite=Lax access cookie.
app.add_middleware(OriginCheckMiddleware)

app.include_router(api_router)

if not _is_prod:
    from app.api.docs import router as docs_router

    app.include_router(docs_router, prefix="/api")

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    # 静的 LP（ランディングページ）を同一ドメインの /lp で配信する（landing/ を Docker で static/lp に同梱）。
    # SPA キャッチオール（/）より先にマウントする必要がある。html=True で /lp・/lp/ とも index.html を返す。
    lp_dir = static_dir / "lp"
    if lp_dir.exists():
        app.mount("/lp", StaticFiles(directory=str(lp_dir), html=True), name="landing")
    app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="frontend")
