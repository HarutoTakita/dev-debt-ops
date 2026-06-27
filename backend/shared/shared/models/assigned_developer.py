"""Shared ``AssignedDeveloper`` ORM — a developer attached to a code/knowledge debt (issue 030).

``assignedDeveloperSchema``（``frontend/src/lib/api/schemas.ts``）に対応。code（028）/ knowledge（030）の
両 debt に紐付くため、多態 FK を避け **判別カラム方式**（``debt_kind`` + ``debt_id``、DB FK は張らない）を採る。
``coverage`` / ``certified_via`` は 029 の ``file_kc``（dev 行）から写す。本テーブルは 030 が新設し 028 と共有する。
"""

import uuid

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class AssignedDeveloper(SQLModel, table=True):
    """A developer associated with one debt row (理解者 / 形式レビュー判定の入力を保持)."""

    __tablename__ = "assigned_developers"
    __table_args__ = (
        UniqueConstraint("debt_kind", "debt_id", "github_handle", name="uq_assigned_developers_debt_handle"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # code / knowledge（どちらの debt 表を指すか）。
    debt_kind: str = Field(index=True, nullable=False)
    # code_debts.id または knowledge_debts.id（判別カラムで解決。DB FK は張らない）。
    debt_id: uuid.UUID = Field(index=True, nullable=False)
    github_handle: str = Field(nullable=False)
    coverage: float = Field(default=0.0, nullable=False)  # = KC(file,dev)（029 file_kc dev 行）
    certified_via: str | None = Field(default=None)  # quiz / authorship / review
