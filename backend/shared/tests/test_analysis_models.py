"""shared 解析基盤モデル（issue 026）のスキーマ単体テスト（DB 不要）。"""

import uuid

from shared.enums import JobStatus
from shared.models import AnalysisRun, RepoFile


def test_analysis_run_defaults() -> None:
    run = AnalysisRun(project_id=uuid.uuid4(), commit_sha="abc123", kind="code_debt_detection")
    assert isinstance(run.id, uuid.UUID)
    assert run.branch == "main"
    assert run.status == JobStatus.QUEUED
    assert run.job_id is None


def test_repo_file_defaults() -> None:
    rf = RepoFile(run_id=uuid.uuid4(), path="src/a.py")
    assert isinstance(rf.id, uuid.UUID)
    assert rf.language is None
    assert rf.loc is None


def test_tablenames() -> None:
    assert AnalysisRun.__tablename__ == "analysis_runs"
    assert RepoFile.__tablename__ == "repo_files"
