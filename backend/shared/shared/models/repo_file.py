"""Shared ``RepoFile`` ORM — File 同一性アンカー（issue 026）.

``analysis_run`` × ファイル。1 run の中で観測された 1 ファイル = 1 行。後続の ``file_debt``（028）/
``file_kc``（029）/ ``dependency``（029。from/to は path）は、すべてこの ``repo_file``（または
``(run_id, path)``）を File の同一性キーとして参照する。File 同一性は ``(run_id, path)`` で同定し、
run/repo 横断の同一性は ``path`` で近似する（rename 追跡は本 issue 範囲外。ADR 0001 参照）。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class RepoFile(SQLModel, table=True):
    """One observed file within an analysis run (run_id × path is unique)."""

    __tablename__ = "repo_files"
    __table_args__ = (UniqueConstraint("run_id", "path", name="uq_repo_files_run_id_path"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="analysis_runs.id", index=True, nullable=False)
    # リポジトリルートからの相対パス（GitHub tree の path。github_git_client.py の TreeItem.path 由来）。
    path: str = Field(nullable=False)
    # 主要言語（fileDebtSchema.language / fileMasterySchema の素材）。判定不能は null。
    language: str | None = Field(default=None)
    # 行数（lines of code）。複雑度・規模指標の素材。
    loc: int | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
