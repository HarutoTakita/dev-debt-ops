from fastapi import APIRouter

from app.api.v1.auth_custom import router as custom_auth_router
from app.core.config import settings
from app.core.security import access_backend, fastapi_users, github_oauth_client
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

router.include_router(custom_auth_router)
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))

if settings.DEMO_MODE_ENABLED:
    # Guest demo login (issue 069): GitHub-less, mounted only when explicitly enabled.
    from app.api.v1.auth_demo import router as demo_auth_router

    router.include_router(demo_auth_router)

if settings.GITHUB_CLIENT_ID:
    router.include_router(
        fastapi_users.get_oauth_router(
            github_oauth_client,
            access_backend,
            settings.SECRET_KEY.get_secret_value(),
            redirect_url=f"{settings.FRONTEND_ORIGIN}/login/callback",
            associate_by_email=True,
        ),
        prefix="/github",
    )
