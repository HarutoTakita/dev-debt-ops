from app.models.oauth_account import OAuthAccount
from app.models.org import Org, OrgMember, OrgRole
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.user import User

# Job / TechStack / AnalysisRun / RepoFile live in `shared` (single source of truth for api +
# service), but api owns the Alembic migrations + DB engine. Import them here — AFTER the app
# models above, so `app.models.base` has already reassigned `SQLModel.metadata` to the
# naming-convention metadata — so Alembic autogenerate and the test `create_all` pick up the
# `jobs` / `tech_stacks` / `analysis_runs` / `repo_files` tables. (issue 018 / 026)
from shared.models import (
    AgentActivity,
    AgentPipeline,
    AnalysisRun,
    AssignedDeveloper,
    CodeDebt,
    DebtTrendPoint,
    Dependency,
    FileKc,
    Job,
    KnowledgeDebt,
    LearningPlan,
    LearningResource,
    LearningStep,
    NarrativeEvidence,
    NarrativeStep,
    QuizAnswer,
    QuizResult,
    QuizSession,
    RepoFile,
    TechStack,
)

__all__ = [
    "AgentActivity",
    "AgentPipeline",
    "AnalysisRun",
    "AssignedDeveloper",
    "CodeDebt",
    "DebtTrendPoint",
    "Dependency",
    "FileKc",
    "Job",
    "KnowledgeDebt",
    "LearningPlan",
    "LearningResource",
    "LearningStep",
    "NarrativeEvidence",
    "NarrativeStep",
    "OAuthAccount",
    "Org",
    "OrgMember",
    "OrgRole",
    "Project",
    "QuizAnswer",
    "QuizResult",
    "QuizSession",
    "RefreshToken",
    "RepoFile",
    "TechStack",
    "User",
]
