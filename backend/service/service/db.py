"""Thin async DB session for the service container.

service does NOT own DDL or migrations — ``api`` owns those via Alembic. service
connects to the same Cloud SQL / Postgres database only to update shared ORM models
(``shared.models.Job`` and domain results) after running a task (issue 016 / 018).

This module wires up the engine + session factory from ``DATABASE_URL``. The engine
is created lazily (no connection until first use), so importing this module never
requires a live database.
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/app")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yield an async session for updating shared ORM models (e.g. ``Job``).

    Used by task handlers (issue 016 / 018) to mark a Job ``COMPLETED`` / ``FAILED``
    and persist its ``result_data``. No-op until those handlers are implemented.
    """
    async with async_session_maker() as session:
        yield session
