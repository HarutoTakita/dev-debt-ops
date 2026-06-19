from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.ENVIRONMENT == "dev")
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
sa_async_session_maker = async_sessionmaker(engine, class_=SAAsyncSession, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """Yield a SQLModel AsyncSession for use as a FastAPI dependency.

    Yields:
        An open `AsyncSession` that is closed automatically on exit.
    """
    async with async_session_maker() as session:
        yield session


async def get_sa_async_session() -> AsyncGenerator[SAAsyncSession]:
    """Yield a plain SQLAlchemy AsyncSession for third-party libraries.

    Used by fastapi-users, whose internal `.execute()` calls emit deprecation
    warnings against SQLModel's `AsyncSession`.

    Yields:
        An open SQLAlchemy `AsyncSession` that is closed automatically on exit.
    """
    async with sa_async_session_maker() as session:
        yield session
