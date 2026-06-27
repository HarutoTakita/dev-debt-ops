"""Shared ``DebtTrendPoint`` ORM — a debt-trend snapshot (issue 031; one per analysis run since 067).

``debtTrendPointSchema``（``frontend/src/lib/api/schemas.ts``）= 地層グラフの 1 点。Overview 配信（031）が
``project_id`` でスコープして読む。**書き込みは 067**（「解析」完了後に ``debt_query.record_trend_snapshot``
が現在の集計を 1 点追加）が所有する。``week`` 列は当初の週ラベルから、067 で解析実行ごとの ISO タイム
スタンプ（並び順キー兼ラベル）に転用した。``project_id`` は索引のみ（FK 無し）。
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class DebtTrendPoint(SQLModel, table=True):
    """One aggregate snapshot of code-debt / knowledge-coverage for a project (one per analysis run)."""

    __tablename__ = "debt_trend_points"
    __table_args__ = (UniqueConstraint("project_id", "week", name="uq_debt_trend_points_project_week"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    week: str = Field(
        nullable=False
    )  # 並び順キー兼ラベル: 067 以降は解析実行ごとの ISO タイムスタンプ（列名は歴史的に week）
    code_debt_score: float = Field(nullable=False)
    knowledge_coverage: float = Field(nullable=False)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
