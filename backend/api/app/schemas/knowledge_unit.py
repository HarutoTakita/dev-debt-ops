"""Knowledge-unit delivery schemas (issue 063) — feature-unit learn→confirm hub. snake_case."""

from pydantic import BaseModel


class KnowledgeUnitOut(BaseModel):
    """One feature unit: learning + confirmation quiz + KC, for the Udemy-style hub."""

    feature_id: str  # 学習プラン生成（feature スコープ）に渡す
    feature_key: str
    name: str
    knowledge_coverage: float  # 055 rollup (avg over the feature's files)
    code_debt_score: float
    file_count: int
    # unstarted / in_progress / verified / needs_review (state machine MVP; ready_to_verify は将来)
    status: str
    learning_plan_id: str | None = None
    quiz_session_id: str | None = None
    quiz_status: str | None = None  # not_started / in_progress / grading / completed


class KnowledgeUnitsOut(BaseModel):
    """Feature units for a project (the learn→confirm hub)."""

    units: list[KnowledgeUnitOut]
