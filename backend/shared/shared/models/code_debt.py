"""Shared ``CodeDebt`` ORM — one detected code-debt finding (issue 028).

コード負債検知パイプライン（``code_debt_detection``）が書き、配信 API（031）が読む正規化テーブル。
フロント契約 ``codeDebtSchema``（``frontend/src/lib/api/schemas.ts``）の ``type`` / ``severity`` /
``status`` / ``code_debt_score`` / ``ai_generation_prob`` 等に対応する。``tech_stack.py`` 雛形
（``uuid4`` PK・``DateTime(timezone=True)``・JSON 列・``UniqueConstraint``、依存は pydantic + sqlmodel のみ）。

- ``project_id`` は ``AnalysisRun`` と同じく **FK を張らず索引のみ**（``projects`` は api 所有で shared
  metadata に無く、service の ``create_all`` が解決できないため）。
- ``run_id`` → ``analysis_runs.id`` は shared 内で解決でき FK を張る（026 の run を時間軸の親に持つ）。
- ``severity`` は ``code_debt_score`` の float→enum 量子化済み値、``priority``（P0–P3）は派生値のため列を持たず
  配信時（031）に算出する。``assigned_developers`` は KC(file,dev)（029/030）依存のため本テーブルは持たない。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class CodeDebt(SQLModel, table=True):
    """A single code-debt finding for one file within one analysis run.

    一意性は ``(run_id, file_path, type)``。同一 run の再処理（at-least-once 再配送）は同キーで upsert され
    二重生成されない。
    """

    __tablename__ = "code_debts"
    __table_args__ = (UniqueConstraint("run_id", "file_path", "type", name="uq_code_debts_run_file_type"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # スコープ。AnalysisRun.project_id と同様 FK 無し・索引のみ（projects は api 所有）。
    project_id: uuid.UUID = Field(index=True, nullable=False)
    # どのスナップショットで検知したか（026 の analysis_run）。shared 内で解決でき FK を張る。
    run_id: uuid.UUID = Field(foreign_key="analysis_runs.id", index=True, nullable=False)
    file_path: str = Field(index=True, nullable=False)
    # codeDebtSchema.type: duplicate / dead / complexity / other。String 保存（native enum を作らない）。
    type: str = Field(nullable=False)
    # code_debt_score の float→enum 量子化済み: critical / high / medium / low。
    severity: str = Field(nullable=False)
    # codeDebtSchema.status: open / in_pr / resolved / dismissed。
    status: str = Field(default="open", nullable=False)
    detected_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    related_pr: str | None = Field(default=None)
    # 「人に頼む」経路で作成した GitHub issue の URL（担当割当 + issue 作成、issue 210）。
    related_issue: str | None = Field(default=None)
    related_adr: str | None = Field(default=None)
    # 検知根拠の人間可読文（"循環的複雑度 24" 等）。
    archaeology_notes: str = Field(default="", nullable=False)
    # 該当コード断片（詳細ビューの file-viewer 表示用）。
    code_snippet: str = Field(default="", nullable=False)
    # 静的解析スコア（縦軸＝コード品質、0..1）。
    code_debt_score: float = Field(nullable=False)
    # KC(file)。029 未実装フェーズの暫定値（0.0）。029 完了後に join で上書き。
    knowledge_coverage: float = Field(default=0.0, nullable=False)
    # Gemini による AI 生成痕跡推定（0..1）。
    ai_generation_prob: float = Field(default=0.0, nullable=False)
    estimated_repay_hours: float = Field(default=0.0, nullable=False)
    # 複雑度・重複・dead の生指標（循環的複雑度・重複クラスタ・到達不能 等）。
    metrics: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
