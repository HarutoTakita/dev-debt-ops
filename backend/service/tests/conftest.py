"""Shared fixtures for service tests (DB-backed task handler).

The service does not own migrations, so tests build the ``jobs`` table directly from the
shared metadata against the Postgres ``test`` DB, and override ``get_session`` /
``get_blob_client`` so the handler writes to the test DB with an in-memory blob.
"""

import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from service.db import get_session
from service.dependencies import get_blob_client
from service.main import app
from shared.blob import MockBlobClient
from shared.models import Job  # noqa: F401 -- register the jobs table on SQLModel.metadata

TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/app").replace(
    "/app", "/test"
)

_mock_blob = MockBlobClient()


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Create the jobs table, override get_session / get_blob_client, drop after."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_blob_client] = lambda: _mock_blob

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield session_maker
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_blob_client, None)


@pytest.fixture
async def session_maker(setup_db: async_sessionmaker[AsyncSession]) -> async_sessionmaker[AsyncSession]:
    """Session maker bound to the test DB (for seeding / asserting Job rows)."""
    return setup_db


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """HTTP client bound to the service ASGI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
