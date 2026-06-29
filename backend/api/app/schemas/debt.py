"""Debt registry delivery schemas (issue 031) — snake_case, matching ``schemas.ts``.

Plain ``BaseModel`` (not ``SharedBaseModel``) so field names stay snake_case on the wire, matching
the frontend ``codeDebtSchema`` / ``knowledgeDebtSchema`` / ``debtItemSchema`` contract exactly
(cf. ``stack.py`` ``TechStackOut``). ``assigned_agent`` is the fixed literal added at delivery time.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AssignedDeveloperOut(BaseModel):
    """A developer attached to a debt (理解者 / 形式レビュー判定の入力)."""

    github_handle: str
    coverage: float
    certified_via: str | None


class CodeDebtOut(BaseModel):
    """A code debt in ``codeDebtSchema`` shape."""

    id: str
    kind: Literal["code"] = "code"
    file_path: str
    repo: str
    type: str
    severity: str
    status: str
    detected_at: datetime
    related_pr: str | None
    related_issue: str | None = None
    related_adr: str | None
    archaeology_notes: str
    code_snippet: str
    code_debt_score: float
    knowledge_coverage: float
    ai_generation_prob: float
    estimated_repay_hours: float
    assigned_agent: Literal["code_debt"] = "code_debt"
    assigned_developers: list[AssignedDeveloperOut]


class KnowledgeDebtOut(BaseModel):
    """A knowledge debt in ``knowledgeDebtSchema`` shape (no ``related_pr``)."""

    id: str
    kind: Literal["knowledge"] = "knowledge"
    file_path: str
    repo: str
    reason: str
    severity: str
    status: str
    detected_at: datetime
    related_adr: str | None
    code_snippet: str
    code_debt_score: float
    knowledge_coverage: float
    ai_generation_prob: float
    estimated_repay_hours: float
    assigned_agent: Literal["knowledge_debt"] = "knowledge_debt"
    assigned_developers: list[AssignedDeveloperOut]


DebtItemOut = CodeDebtOut | KnowledgeDebtOut


class DebtListOut(BaseModel):
    """``debtListSchema`` shape: filtered debts + post-filter total."""

    debts: list[DebtItemOut]
    total: int


class DebtUpdate(BaseModel):
    """Partial update (PATCH). ``status`` per kind; ``assignee`` upserts an assigned developer."""

    status: str | None = None
    assignee_github_handle: str | None = None
    assignee_certified_via: str | None = None
    assignee_coverage: float | None = None
