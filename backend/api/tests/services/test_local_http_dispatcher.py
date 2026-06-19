"""LocalHttpDispatcher: POSTs to the service container and is selected in local-service mode."""

import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services.dependencies import get_task_dispatcher
from app.services.local_http_dispatcher import LocalHttpDispatcher


async def test_dispatch_posts_to_service_tasks_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _StubResponse:
        status_code = 200

    class _StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_StubClient":
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def post(self, url: str, json: dict) -> _StubResponse:
            captured["url"] = url
            captured["json"] = json
            return _StubResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

    dispatcher = LocalHttpDispatcher("http://service:8000/")
    await dispatcher.dispatch("stack_analysis", {"jobId": "j1", "owner": "acme"}, dedup_key="j1")
    # dispatch is fire-and-forget; let the detached POST task run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert captured["url"] == "http://service:8000/tasks/stack_analysis"
    assert captured["json"]["owner"] == "acme"


def test_get_task_dispatcher_returns_local_http_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "USE_LOCAL_SERVICE", True)
    monkeypatch.setattr(settings, "SERVICE_TASKS_URL", "http://service:8000")
    assert isinstance(get_task_dispatcher(), LocalHttpDispatcher)
    # local-service mode also disables the in-process mock-worker.
    assert settings.use_mock_worker() is False
    assert settings.use_mock_queue() is False
