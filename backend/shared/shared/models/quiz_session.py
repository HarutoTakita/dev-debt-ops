"""Shared ``QuizSession`` ORM — one quiz attempt for a low-KC file (issue 034).

``quizSessionSchema``（``frontend/src/lib/api/schemas.ts``）に対応。生成パイプラインが ``questions`` を埋め、
採点パイプラインが ``status``/``score`` を更新する。``answer_key`` は正答/採点基準の **非公開**列で、配信時には
出さない（API は ``questions`` から除去して返す）。``project_id`` は索引のみ（FK 無し、Job.project_id 流儀）。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


class QuizSession(SQLModel, table=True):
    """A quiz session (questions + lifecycle) for one file × developer."""

    __tablename__ = "quiz_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    developer_id: uuid.UUID = Field(index=True, nullable=False)  # = users.id（認可で current_user に束ねる）
    file_path: str = Field(nullable=False)
    repo_full_name: str = Field(default="", nullable=False)
    # 計測粒度（issue 054）。``feature`` のとき対象は ``feature_id`` で解決し ``file_path`` は代表/空。
    # default ``file`` で既存のファイル単位受験は後方互換。
    granularity: str = Field(default="file", nullable=False)
    feature_id: uuid.UUID | None = Field(default=None)  # granularity="feature" のとき features.id
    # 機能の stable slug（features.key）。features.id は run 毎に再生成されるため、再解析をまたいで
    # クイズを機能に結び付ける解決/dedup はこの key で行う（FeatureFlag と同じ流儀）。旧行は None で
    # feature_id フォールバック。
    feature_key: str | None = Field(default=None, index=True)
    is_baseline: bool = Field(default=False, nullable=False)  # 初回ベースライン受験フラグ（自動生成 / 集計用）
    # 要再受験（stale）。機能のファイル集合が再解析で変わると true にし、UI が再受験を促す（返済ループ駆動）。
    # 新しい retest セッションは既定 false でリセットされる。
    stale: bool = Field(default=False, nullable=False)
    # 再テスト系譜（#6）。フィルタ再テストで生成されたセッションは元セッションの id を指す（chain の根）。
    origin_session_id: uuid.UUID | None = Field(default=None, index=True)
    retest_mode: str | None = Field(default=None)  # None=通常 / "flagged"=フラグのみ / "wrong"=全回誤答のみ
    # not_started / in_progress / grading / completed（小文字。Job の JobStatus 大文字とは別系列）。
    status: str = Field(default="not_started", nullable=False)
    score: float | None = Field(default=None)
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # 生成済み quizQuestion 配列（配信形）。
    questions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # 正答/採点基準（非公開。配信に出さない）。{question_id: {answer, rubric}}。
    answer_key: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_kc: float | None = Field(default=None)  # 受験対象選定時の KC スナップショット（内部用）
