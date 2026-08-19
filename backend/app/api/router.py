from fastapi import APIRouter

from app.api.jobs import router as jobs_router
from app.api.introductions import router as introductions_router
from app.api.plugin_two import router as plugin_two_router

api_router = APIRouter()
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(
    introductions_router, prefix="/introductions", tags=["introductions"]
)
api_router.include_router(plugin_two_router, prefix="/plugin-two", tags=["plugin-two"])
