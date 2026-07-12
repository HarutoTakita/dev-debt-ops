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
    # 学習プランの進捗（完了ステップ数 / 総ステップ数）。一覧のプログレスバー表示に使う（プラン未生成なら 0/0）。
    learning_steps_done: int = 0
    learning_steps_total: int = 0
    flagged: bool = False  # このユーザーがフラグを付けた単元か（フラグ付きは一覧上部にソート）
    # 要再受験（stale）: 再解析でこの機能のファイル集合が変わり、既存のクイズ/学習が陳腐化した可能性がある。
    stale: bool = False


class KnowledgeUnitsOut(BaseModel):
    """Feature units for a project (the learn→confirm hub)."""

    units: list[KnowledgeUnitOut]


class FeatureFlagIn(BaseModel):
    """Set/clear the caller's flag on a feature unit (flagged units sort to the top)."""

    flagged: bool
