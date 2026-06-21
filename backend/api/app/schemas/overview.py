"""Overview aggregation delivery schemas (issue 031) — snake_case, matching ``overviewSchema``."""

from datetime import datetime

from pydantic import BaseModel


class FileDebtOut(BaseModel):
    """One file as a two-axis point (``fileDebtSchema``)."""

    path: str
    language: str
    code_debt_score: float
    knowledge_coverage: float
    business_impact: float
    priority: str  # P0..P3


class FeatureDebtOut(BaseModel):
    """One feature/folder rolled-up node (``featureDebtSchema``, issue 055).

    For ``granularity=feature`` ``key``/``name`` come from ``features``; for ``granularity=folder``
    they are the directory path. ``knowledge_coverage`` is the average over the node's files;
    ``weakest_file`` is the lowest-KC file (the understanding-debt focus).
    """

    key: str
    name: str
    granularity: str
    code_debt_score: float
    knowledge_coverage: float
    priority: str  # P0..P3
    file_count: int
    weakest_file: str | None = None


class DebtTrendPointOut(BaseModel):
    """One weekly trend point (``debtTrendPointSchema``)."""

    week: str
    code_debt_score: float
    knowledge_coverage: float


class WeeklyActivityOut(BaseModel):
    """This-week activity counters (``weeklyActivitySchema``)."""

    code_agent_prs: int
    code_agent_merged: int
    knowledge_agent_quizzes: int
    knowledge_agent_passed: int


class OverviewOut(BaseModel):
    """Overview dashboard payload (``overviewSchema``)."""

    org: str
    generated_at: datetime
    granularity: str = "file"
    files: list[FileDebtOut]
    # Rolled-up nodes when granularity is feature/folder (empty for granularity=file). issue 055.
    features: list[FeatureDebtOut] = []
    trend: list[DebtTrendPointOut]
    activity: WeeklyActivityOut
