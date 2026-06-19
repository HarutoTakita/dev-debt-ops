from app.models.oauth_account import OAuthAccount
from app.models.org import Org, OrgMember, OrgRole
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.user import User

# Job + TechStack live in `shared` (single source of truth for api + service), but api owns
# the Alembic migrations + DB engine. Import them here — AFTER the app models above, so
# `app.models.base` has already reassigned `SQLModel.metadata` to the naming-convention
# metadata — so Alembic autogenerate and the test `create_all` pick up the `jobs` /
# `tech_stacks` tables. (issue 018 promoted TechStack from `app.models` to `shared.models`.)
from shared.models import Job, TechStack

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
