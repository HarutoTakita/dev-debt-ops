from app.models.oauth_account import OAuthAccount
from app.models.org import Org, OrgMember, OrgRole
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.tech_stack import TechStack
from app.models.user import User

# Job lives in `shared` (single source of truth for api + service), but api owns the
# Alembic migrations + DB engine. Import it here — AFTER the app models above, so
# `app.models.base` has already reassigned `SQLModel.metadata` to the naming-convention
# metadata — so Alembic autogenerate and the test `create_all` pick up the `jobs` table.
from shared.models import Job

__all__ = [
    "Job",
    "OAuthAccount",
    "Org",
    "OrgMember",
    "OrgRole",
    "Project",
    "RefreshToken",
    "TechStack",
    "User",
]
