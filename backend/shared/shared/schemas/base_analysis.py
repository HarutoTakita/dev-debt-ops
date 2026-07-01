"""Base repository-analysis ("元データ") schema — the output of the Base Analysis Agent (issue 266).

Agent-first re-architecture: the main repository analysis IS an agent. It runs FIRST and emits ONE
canonical, *qualitative* ``BaseAnalysis`` (features / key concepts / risk narrative), which the
downstream blocks then format and enhance into the screen tables.

Deliberately **carries no hard numbers**. KC (git blame), ``code_debt_score`` / complexity metrics
and ``ai_generation_prob`` are *measurements* attached by deterministic program blocks
(``kc_analysis`` / ``code_analysis`` / ``estimate_ai_generation``) — never authored by the LLM. The
agent authors *what* and *why* (grouping, rationale, learning concepts, qualitative severity);
deterministic code authors *how much*.

Pure Pydantic (no ORM). Lives in ``shared`` because both ``service`` (produces + persists it) and,
later, ``api`` (may surface it) reference it — same placement rationale as ``agentic_analysis``.
"""

from pydantic import BaseModel, Field


class BaseFeatureFile(BaseModel):
    """One file the agent assigns to a feature (path must be a real repo path)."""

    path: str
    confidence: float = 1.0


class BaseFeature(BaseModel):
    """A semantic product capability (auth / billing / analysis pipeline …), not a folder."""

    key: str  # short, stable, lowercase kebab/snake slug — trackable across runs
    name: str
    description: str = ""
    files: list[BaseFeatureFile] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)  # learning terms (seed for quiz/plan)
    risk_notes: str = ""  # qualitative hotspot/understanding-risk narrative (NOT a score)


class BaseCodeFinding(BaseModel):
    """A qualitative code-quality concern. Numbers/metrics are attached deterministically downstream."""

    file_path: str
    type: str = "other"  # complexity | duplicate | dead | security | smell | other
    severity: str = "medium"  # low | medium | high — the agent's qualitative call (advisory)
    rationale: str = ""  # 日本語 narrative → enriches CodeDebt.archaeology_notes
    snippet: str = ""


class BaseKnowledgeFinding(BaseModel):
    """A qualitative understanding-risk signal. Coverage numbers come from deterministic file_kc."""

    file_path: str
    reason: str = "other"  # ai_generated | author_left | no_review | other (aligns w/ knowledge_debts.reason)
    rationale: str = ""  # → enriches KnowledgeDebt.detection_notes
    risk_signal: str = ""


class BaseAnalysis(BaseModel):
    """The canonical qualitative base analysis produced by the Base Analysis Agent."""

    features: list[BaseFeature] = Field(default_factory=list)
    code_findings: list[BaseCodeFinding] = Field(default_factory=list)
    knowledge_findings: list[BaseKnowledgeFinding] = Field(default_factory=list)
    stack_terms: list[str] = Field(default_factory=list)  # optional hints; deterministic populate is authoritative
    summary: str = ""

    def is_empty(self) -> bool:
        """True when the agent produced nothing usable (→ downstream falls back to deterministic)."""
        return not (self.features or self.code_findings or self.knowledge_findings)
