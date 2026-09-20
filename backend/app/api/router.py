from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    competition_discovery,
    competitions,
    conferences,
    health,
    home,
    policies,
    recommendations,
    stats,
    tags,
    universities,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(home.router)
api_router.include_router(competitions.router)
api_router.include_router(conferences.router)
api_router.include_router(competition_discovery.router)
api_router.include_router(universities.router)
api_router.include_router(recommendations.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(admin.router)
api_router.include_router(tags.router)
api_router.include_router(stats.router)
api_router.include_router(policies.router)
