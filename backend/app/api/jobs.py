from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.schemas.job import JobEvaluateResponse, JobPayload
from app.services.coze_client import (
    CozeConfigurationError,
    CozeRequestError,
    CozeResponseError,
    CozeTimeoutError,
)
from app.services.job_service import JobService
from app.services.introduction_service import schedule_introduction_for_evaluation

router = APIRouter()


@router.post(
    "/evaluate",
    response_model=JobEvaluateResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def evaluate_job(
    payload: JobPayload,
    background_tasks: BackgroundTasks,
) -> JobEvaluateResponse:
    try:
        result = await JobService().evaluate(payload)
        schedule_introduction_for_evaluation(
            background_tasks=background_tasks,
            payload=payload,
            coze_output=result.coze_output,
            application_id=result.application_database_id,
        )
        return result.response
    except CozeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except CozeTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except (CozeRequestError, CozeResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"岗位数据保存失败: {exc}",
        ) from exc


@router.post(
    "/bulk-evaluate",
    response_model=JobEvaluateResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def bulk_evaluate_job(payload: JobPayload) -> JobEvaluateResponse:
    """保存海投岗位并返回固定通过分，不调用任何 Coze Workflow。"""
    try:
        result = await JobService().bulk_evaluate(payload)
        return result.response
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"岗位数据保存失败: {exc}",
        ) from exc
