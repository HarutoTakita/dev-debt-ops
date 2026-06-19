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
    files: list[FileDebtOut]
    trend: list[DebtTrendPointOut]
    activity: WeeklyActivityOut
