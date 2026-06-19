from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.debts import router as debts_router
from app.api.v1.github import router as github_router
from app.api.v1.health import router as health_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.orgs import router as orgs_router
from app.api.v1.projects import router as projects_router
from app.api.v1.stack import router as stack_router
from app.api.v1.users import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(orgs_router)
api_router.include_router(projects_router)
api_router.include_router(debts_router)
api_router.include_router(github_router)
api_router.include_router(stack_router)
api_router.include_router(jobs_router)
