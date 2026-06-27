"""Shared ``AnalysisRun`` ORM — one row per repository-snapshot analysis (issue 026).

全解析ドメイン（028 以降）が共有する「どの project の、どの commit を、どの種別で解析したか」の軸。
api が読み（集計・配信）、service が書く（解析 DML）双方から ``from shared.models import AnalysisRun``
で参照する。Alembic マイグレーションと DB エンジン/セッションは api が所有（0006 がこのテーブルを作る）。

``kind`` / ``status`` は ``Job.job_type`` / ``Job.status`` と同じく **String 保存**（native PG enum を作らない）。
``kind`` は ``JobType`` 値、``status`` は ``JobStatus`` 値に揃えるが、後続 issue が新 ``kind`` を増やしても
マイグレーション不要にするため列型は緩く保つ。id は ``shared`` を軽量に保つため ``uuid4`` default
（``tech_stack.py`` / ``job.py`` と同形。api 側の ``uuid7_pk()`` は使わない）。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, func
from sqlmodel import Field, SQLModel

from shared.enums import JobStatus


class AnalysisRun(SQLModel, table=True):
    """A single analysis execution against a repository snapshot (project × commit × kind).

    後続の ``repo_file`` / ``file_debt`` / ``file_kc`` / ``dependency`` はこの run を時間軸の親に持つ。
    trend（週次推移）は同 project の run を ``commit_sha`` + ``created_at`` で並べて導出する。
    """

    __tablename__ = "analysis_runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # 解析対象 project（1 project = 1 repo）。``projects`` は api 所有テーブルで ``shared`` の
    # metadata には無いため、``Job.project_id`` と同じく ORM レベルの FK は張らない（張ると
    # service 側の ``SQLModel.metadata.create_all`` が projects を解決できず NoReferencedTableError）。
    # 参照整合性が必要なら api 所有の Alembic 側で FK を足す（本 issue では Job 流儀に倣い索引のみ）。
    project_id: uuid.UUID = Field(index=True, nullable=False)
    # 解析した時点の commit。冪等・trend スナップショットのキー（037 が同 commit の重複 run 抑止に使う）。
    commit_sha: str = Field(index=True, nullable=False)
    # server_default("main") so non-ORM inserts (constructed statements) can't NOT-NULL-violate
    # when the column is omitted (issue-042).
    branch: str = Field(default="main", sa_column_kwargs={"server_default": "main"}, nullable=False)
    # 解析種別。値は JobType（lowercase snake_case）に揃える。後続 issue が値を入れる。
    kind: str = Field(sa_type=String, index=True, nullable=False)
    # この run を生成した非同期 Job（手動 / 定期どちらの run か追える）。
    job_id: uuid.UUID | None = Field(default=None, foreign_key="jobs.id", index=True)
    # run のライフサイクル。値は JobStatus（UPPERCASE）に揃える。
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_type=String, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
