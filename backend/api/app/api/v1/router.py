from fastapi import APIRouter

from app.api.v1.agents import router as agents_router
from app.api.v1.auth import router as auth_router
from app.api.v1.debts import router as debts_router
from app.api.v1.features import router as features_router
from app.api.v1.galaxy import router as galaxy_router
from app.api.v1.github import router as github_router
from app.api.v1.health import router as health_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.kc import router as kc_router
from app.api.v1.knowledge_debts import router as knowledge_debts_router
from app.api.v1.learning import router as learning_router
from app.api.v1.orgs import router as orgs_router
from app.api.v1.overview import router as overview_router
from app.api.v1.projects import router as projects_router
from app.api.v1.quizzes import router as quizzes_router
from app.api.v1.stack import router as stack_router
from app.api.v1.users import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(orgs_router)
api_router.include_router(projects_router)
api_router.include_router(debts_router)
api_router.include_router(kc_router)
api_router.include_router(knowledge_debts_router)
api_router.include_router(overview_router)
api_router.include_router(galaxy_router)
api_router.include_router(features_router)
api_router.include_router(quizzes_router)
api_router.include_router(learning_router)
api_router.include_router(agents_router)
api_router.include_router(github_router)
api_router.include_router(stack_router)
api_router.include_router(jobs_router)
