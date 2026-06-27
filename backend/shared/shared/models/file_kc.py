"""Shared ``FileKc`` ORM — Knowledge Coverage per file (issue 029).

KC(file,dev)（``dev_id`` 非 NULL）と集計 KC(file)（``dev_id IS NULL``）を 1 テーブルで両立させる。
``kc_analysis`` パイプラインが git authorship/blame から算出して書き、Galaxy 配信（032）が読む。
フロント契約 ``fileMasterySchema``（``frontend/src/lib/api/schemas.ts``）に対応する。

行の種別は 3 つあり、Postgres の NULL 区別を避けるため**互いに素な 3 つの部分ユニーク索引**で一意化する
（``create_all`` でも作られ、upsert の競合ターゲットになる）:
- dev 行（突合済み, dev_id あり）→ ``(run_id, file_path, dev_id)``
- dev 行（未突合・handle のみ, dev_id NULL かつ handle あり）→ ``(run_id, file_path, github_handle)``
- 集計行（dev_id NULL かつ handle NULL）→ ``(run_id, file_path)``

これにより未突合 author の dev 行（dev_id NULL・handle あり）と集計行（dev_id NULL・handle なし）が衝突しない。
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, func, text
from sqlmodel import Field, SQLModel


class FileKc(SQLModel, table=True):
    """Knowledge Coverage for one file — either per-developer or the file-level aggregate."""

    __tablename__ = "file_kc"
    __table_args__ = (
        Index(
            "uq_file_kc_dev",
            "run_id",
            "file_path",
            "dev_id",
            unique=True,
            postgresql_where=text("dev_id IS NOT NULL"),
        ),
        Index(
            "uq_file_kc_handle",
            "run_id",
            "file_path",
            "github_handle",
            unique=True,
            postgresql_where=text("dev_id IS NULL AND github_handle IS NOT NULL"),
        ),
        Index(
            "uq_file_kc_agg",
            "run_id",
            "file_path",
            unique=True,
            postgresql_where=text("dev_id IS NULL AND github_handle IS NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # スナップショット軸（026 の analysis_run）。shared 内で解決でき FK を張る。
    run_id: uuid.UUID = Field(foreign_key="analysis_runs.id", index=True, nullable=False)
    file_path: str = Field(index=True, nullable=False)
    # 星系 = ディレクトリ（fileMasterySchema.module）。032 の星系集計に使う。
    module: str = Field(default="", nullable=False)
    # None = 集計 KC(file) 行 / 非 None = KC(file,dev) 行。users.id 主（026 ADR）。FK は張らない。
    dev_id: uuid.UUID | None = Field(default=None, index=True)
    # 027 の authorship 突合結果。users.id 未突合 author は handle のみ保持（捏造しない）。
    github_handle: str | None = Field(default=None)
    kc: float = Field(nullable=False)  # 0..1
    # kc から導出: star / dim_star / black_hole / unexplored。
    mastery: str = Field(nullable=False)
    # quiz / authorship / review（nullable）。本 issue は authorship。quiz は 034 が更新。
    certified_via: str | None = Field(default=None)
    computed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
