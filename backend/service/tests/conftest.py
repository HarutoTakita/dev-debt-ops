"""Shared fixtures for service tests."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from service.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """HTTP client bound to the service ASGI app (no network / DB)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
