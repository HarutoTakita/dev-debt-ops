"""Shared ``DebtTrendPoint`` ORM — a weekly debt-trend snapshot (issue 031).

``debtTrendPointSchema``（``frontend/src/lib/api/schemas.ts``）= 地層グラフの 1 週分。Overview 配信（031）が
``project_id`` でスコープして読む。**書き込み（週次スナップショット生成）は 037**（定期スキャンが
``analysis_run`` 時系列から生成）が所有し、本 issue は読み取りのみ。``project_id`` は索引のみ（FK 無し）。
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class DebtTrendPoint(SQLModel, table=True):
    """One weekly aggregate snapshot of code-debt / knowledge-coverage for a project."""

    __tablename__ = "debt_trend_points"
    __table_args__ = (UniqueConstraint("project_id", "week", name="uq_debt_trend_points_project_week"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    week: str = Field(nullable=False)  # ISO 週 or ラベル
    code_debt_score: float = Field(nullable=False)
    knowledge_coverage: float = Field(nullable=False)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
