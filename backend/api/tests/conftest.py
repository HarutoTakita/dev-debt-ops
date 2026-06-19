import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import db as app_db
from app.core.config import settings
from app.core.db import get_async_session, get_sa_async_session
from app.main import app
from app.models import Org, OrgMember, Project, User  # noqa: F401

TEST_DATABASE_URL = settings.DATABASE_URL.replace("/app", "/test")

# Partial unique indexes that can't be declared in SQLModel models
_EXTRA_DDL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_orgs_slug_active ON orgs (slug) WHERE deleted_at IS NULL",
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_members_user_org_active"
        " ON org_members (user_id, org_id) WHERE deleted_at IS NULL"
    ),
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_org_slug_active"
        " ON projects (org_id, slug) WHERE deleted_at IS NULL"
    ),
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_org_repo_active"
        " ON projects (org_id, repo_full_name) WHERE deleted_at IS NULL"
    ),
]


@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after. Fresh engine per test to avoid asyncpg connection reuse issues."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    test_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    test_sa_session_maker = async_sessionmaker(engine, class_=SAAsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session_maker() as session:
            yield session

    async def override_get_sa_session():
        async with test_sa_session_maker() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_get_session
    app.dependency_overrides[get_sa_async_session] = override_get_sa_session

    original_session_maker = app_db.async_session_maker
    app_db.async_session_maker = test_session_maker
    original_sa_session_maker = app_db.sa_async_session_maker
    app_db.sa_async_session_maker = test_sa_session_maker

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        for ddl in _EXTRA_DDL:
            await conn.execute(text(ddl))
    yield
    # dispose() before drop_all prevents DeadlockDetectedError from pooled connections
    # holding RowExclusiveLock against DROP TABLE's AccessExclusiveLock.
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()
    app_db.async_session_maker = original_session_maker
    app_db.sa_async_session_maker = original_sa_session_maker
    app.dependency_overrides.pop(get_async_session, None)
    app.dependency_overrides.pop(get_sa_async_session, None)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authenticated_client(client: AsyncClient) -> AsyncClient:
    """Register a user, login, return client with auth cookies."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "testpassword123", "display_name": "Test User"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": "user@example.com", "password": "testpassword123"},
    )
    client.cookies = login_response.cookies
    return client


async def register_and_login(client: AsyncClient, email: str, password: str = "testpassword123") -> AsyncClient:
    """Register a user, login, set cookies on client, return client."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    client.cookies = login_response.cookies
    return client


@pytest.fixture
async def user_with_org(authenticated_client: AsyncClient) -> tuple[AsyncClient, dict]:
    """Return authenticated client + a non-personal org."""
    response = await authenticated_client.post(
        "/api/v1/orgs",
        json={"name": "Test Org", "slug": "test-org"},
    )
    return authenticated_client, response.json()
