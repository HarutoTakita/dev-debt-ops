from fastapi import APIRouter

from app.api.v1.auth_custom import router as custom_auth_router
from app.core.security import fastapi_users
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

router.include_router(custom_auth_router)
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))
