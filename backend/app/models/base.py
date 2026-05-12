import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, MetaData, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlmodel import Field, SQLModel
from uuid_utils.compat import uuid7

# Naming conventions for Alembic autogenerate
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    """SQLAlchemy declarative base for models that need native SA features (e.g. fastapi-users)."""

    metadata = MetaData(naming_convention=convention)


# Share metadata so Alembic sees both SQLAlchemy (Base) and SQLModel tables
SQLModel.metadata = Base.metadata


def generate_uuid7() -> uuid.UUID:
    """Generate a new UUIDv7 (time-ordered)."""
    return uuid7()


# --- Field factories for SQLModel table models ---


def uuid7_pk() -> uuid.UUID:
    """Return a SQLModel Field configured as a UUIDv7 primary key.

    Returns a `Field` with `primary_key=True` and `default_factory=generate_uuid7`, making
    it the canonical id column definition for all SQLModel table models in this project.
    """
    return Field(default_factory=generate_uuid7, primary_key=True)


def created_at_field() -> datetime:
    """Timestamped field: server-populated on INSERT. Timezone-aware."""
    return Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))


def updated_at_field() -> datetime:
    """Timestamped field: server-populated on INSERT and auto-updated on UPDATE. Timezone-aware."""
    return Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


def deleted_at_field() -> datetime | None:
    """Nullable soft-delete timestamp field. `NULL` means not deleted. Timezone-aware."""
    return Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


# --- Column factories for native SQLAlchemy models (e.g. User) ---


def sa_created_at() -> Mapped[datetime]:
    """Native SQLAlchemy analog — timestamped column: server-populated on INSERT. Timezone-aware."""
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def sa_updated_at() -> Mapped[datetime]:
    """Native SQLAlchemy analog — server-populated on INSERT and auto-updated on UPDATE. Timezone-aware."""
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def sa_deleted_at() -> Mapped[datetime | None]:
    """Native SQLAlchemy analog — nullable soft-delete timestamp column. `NULL` means not deleted. Timezone-aware."""
    return mapped_column(DateTime(timezone=True), nullable=True)
