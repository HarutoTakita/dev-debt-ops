"""Twin-Agent delivery schemas (issue 036) — snake_case, matching the agent Zod contract."""

from datetime import datetime

from pydantic import BaseModel


class AgentProfileOut(BaseModel):
    """A static agent persona (``agentProfileSchema``)."""

    kind: str
    name: str
    role: str
    accent: str
    tagline: str


class NarrativeEvidenceOut(BaseModel):
    """Archaeology evidence (``narrativeEvidenceSchema``)."""

    type: str
    label: str
    detail: str | None
    href: str | None


class NarrativeStepOut(BaseModel):
    """A first-person thinking step (``narrativeStepSchema``)."""

    id: str
    status: str
    message: str
    evidence: list[NarrativeEvidenceOut]
    created_at: datetime


class AgentActivityOut(BaseModel):
    """A narrative activity (``agentActivitySchema``)."""

    id: str
    kind: str
    headline: str
    steps: list[NarrativeStepOut]
    pipeline_id: str
    created_at: datetime


class AgentPipelineOut(BaseModel):
    """The 5-stage pipeline (``agentPipelineSchema``); ``stages`` passes through the stored JSON."""

    id: str
    kind: str
    stages: list[dict]
