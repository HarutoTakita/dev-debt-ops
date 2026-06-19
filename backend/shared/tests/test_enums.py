"""Smoke tests for the shared package (enums import + Job model importable)."""

from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import Job


def test_job_status_values_are_uppercase() -> None:
    """JobStatus values are UPPERCASE per issue 016."""
    assert JobStatus.QUEUED.value == "QUEUED"
    assert JobStatus.PROCESSING.value == "PROCESSING"
    assert JobStatus.COMPLETED.value == "COMPLETED"
    assert JobStatus.FAILED.value == "FAILED"
    assert JobStatus.CANCELLED.value == "CANCELLED"


def test_job_type_stack_analysis_pipeline_name() -> None:
    """JobType.STACK_ANALYSIS maps to the ``stack-analysis`` pipeline path."""
    assert JobType.STACK_ANALYSIS.value == "stack_analysis"
    assert JobType.STACK_ANALYSIS.value.replace("_", "-") == "stack-analysis"


def test_result_status_members() -> None:
    """ResultStatus has exactly the terminal states."""
    assert set(ResultStatus) == {ResultStatus.COMPLETED, ResultStatus.FAILED, ResultStatus.PARTIAL}


def test_job_model_is_importable() -> None:
    """``from shared.models import Job`` works (shared owns the table definition)."""
    assert Job.__tablename__ == "jobs"
