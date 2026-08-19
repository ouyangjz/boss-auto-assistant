from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.schemas.introduction import (
    IntroductionGenerateResponse,
    IntroductionTaskContext,
)
from app.services.introduction_service import schedule_introduction_generation

router = APIRouter()


@router.post(
    "/generate",
    response_model=IntroductionGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_introduction(
    payload: IntroductionTaskContext,
    background_tasks: BackgroundTasks,
) -> IntroductionGenerateResponse:
    """独立调度 Coze 自我介绍 Workflow，并在完成后推送聊天助手。"""
    if payload.match_score < settings.match_threshold:
        raise HTTPException(
            status_code=422,
            detail=(
                f"match_score 必须大于等于阈值 {settings.match_threshold}"
            ),
        )
    if not payload.self_intro_context:
        raise HTTPException(
            status_code=422,
            detail="self_intro_context 不能为空",
        )

    task_id = schedule_introduction_generation(background_tasks, payload)
    return IntroductionGenerateResponse(success=True, task_id=task_id)
