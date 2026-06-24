"""Learning-plan delivery schemas (issue 035) — snake_case, matching ``learningPlanSchema``."""

import uuid

from pydantic import BaseModel

from shared.enums import JobStatus


class LearningResourceOut(BaseModel):
    """A learning resource (``learningResourceSchema``)."""

    id: str
    origin: str
    section: str  # code（このコードを理解する）/ stack（技術スタックを学ぶ）issue 068
    kind: str
    title: str
    summary: str  # 「何を・なぜ理解すべきか」の説明（issue 068）
    tech: str  # 学べるテックスタックのタグ（stack 資源のみ・issue 068）
    source_ref: str | None
    url: str | None
    estimated_minutes: int | None
    priority: str
    dormant_days: int | None


class LearningStepOut(BaseModel):
    """An ordered step (``learningStepSchema``)."""

    order: int
    resource: LearningResourceOut
    completed: bool


class LearningPlanOut(BaseModel):
    """A learning plan (``learningPlanSchema``)."""

    id: str
    gap_concepts: list[str]
    steps: list[LearningStepOut]
    estimated_total_minutes: int


class LearningPlanJobOut(BaseModel):
    """``POST .../learning/plans`` response: enqueued job + the (pre-created) plan id to poll for."""

    job_id: uuid.UUID
    status: JobStatus
    plan_id: uuid.UUID


class GeneratePlanIn(BaseModel):
    """Body for ``POST .../learning/plans`` (used when no ``attempt_id`` resolves the gaps)."""

    gap_concepts: list[str] = []
    feature_id: str | None = None  # 機能単元にプランを紐付ける（issue 063）


class BaselinePlansOut(BaseModel):
    """Summary for ``POST .../baseline-plans`` (issue 064) — one plan per clustered feature."""

    created: int
    job_ids: list[str]


class StepPatchIn(BaseModel):
    """Body for ``PATCH .../learning/plans/{id}/steps/{order}``."""

    completed: bool
