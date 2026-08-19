from fastapi import APIRouter

from app.api.jobs import router as jobs_router
from app.api.introductions import router as introductions_router
from app.api.chat_assistant import router as chat_assistant_router

api_router = APIRouter()
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(
    introductions_router, prefix="/introductions", tags=["introductions"]
)
api_router.include_router(
    chat_assistant_router,
    prefix="/chat-assistant-extension",
    tags=["chat-assistant-extension"],
)
