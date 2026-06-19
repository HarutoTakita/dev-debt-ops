"""Shared ``KnowledgeDebt`` ORM — one detected knowledge-debt finding (issue 030).

知識負債検知パイプライン（``knowledge_debt_detection``）が書き、配信 API（031）が読む。
フロント契約 ``knowledgeDebtSchema``（``frontend/src/lib/api/schemas.ts``）に対応する。``code_debts``（028）と
ほぼ同構造だが、``reason``（type ではない）/ ``related_pr`` を持たない / ``status`` に ``in_pr``・``dismissed`` が無い /
``detection_notes``（配信契約外の検知根拠）という差分を持つ。

``project_id`` は ``code_debts`` と同じく索引のみ（FK 無し）。``run_id`` → ``analysis_runs.id`` は FK。
``knowledge_coverage`` は 029 の ``file_kc``（集計行）から join して埋める（029 未算出時は暫定 0.0）。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class KnowledgeDebt(SQLModel, table=True):
    """A single knowledge-debt finding for one file within one analysis run.

    一意性は ``(run_id, file_path, reason)``。同一 run の再処理は同キーで upsert され二重生成されない。
    """

    __tablename__ = "knowledge_debts"
    __table_args__ = (UniqueConstraint("run_id", "file_path", "reason", name="uq_knowledge_debts_run_file_reason"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)  # 索引のみ（projects は api 所有）
    run_id: uuid.UUID = Field(foreign_key="analysis_runs.id", index=True, nullable=False)
    file_path: str = Field(index=True, nullable=False)
    repo: str = Field(default="", nullable=False)
    # ai_generated / author_left / no_review / other。String 保存（native enum を作らない）。
    reason: str = Field(nullable=False)
    # code_debt_score の float→enum 量子化: critical / high / medium / low。
    severity: str = Field(nullable=False)
    # open / in_progress / resolved（code 側の in_pr / dismissed は持たない）。
    status: str = Field(default="open", nullable=False)
    detected_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    related_adr: str | None = Field(default=None)  # related_pr は持たない
    code_snippet: str = Field(default="", nullable=False)
    code_debt_score: float = Field(default=0.0, nullable=False)
    # = KC(file)。029 file_kc 集計行から join して埋める（未算出時は暫定 0.0）。
    knowledge_coverage: float = Field(default=0.0, nullable=False)
    ai_generation_prob: float = Field(default=0.0, nullable=False)
    estimated_repay_hours: float = Field(default=0.0, nullable=False)
    # 検知根拠（配信契約 knowledgeDebtSchema には無い。配信時 031 は出さない）。
    detection_notes: str = Field(default="", nullable=False)
    metrics: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
