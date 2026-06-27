"""Shared ``Dependency`` ORM — intra-repo import edge (wormhole) for one run (issue 029).

027 の依存抽出ヘルパ（``DependencyEdge``）が返すリポジトリ内ファイル間依存を永続化する。
``kc_analysis`` パイプラインが書き、Galaxy 配信（032）が ``wormholeSchema``（``from`` / ``to``）へ射影する。
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class Dependency(SQLModel, table=True):
    """A directed intra-repo import edge (``from_path`` imports ``to_path``) within one run."""

    __tablename__ = "dependencies"
    __table_args__ = (UniqueConstraint("run_id", "from_path", "to_path", name="uq_dependencies_run_from_to"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="analysis_runs.id", index=True, nullable=False)
    from_path: str = Field(nullable=False)
    to_path: str = Field(nullable=False)
    computed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
