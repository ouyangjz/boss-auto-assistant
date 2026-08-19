from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.dashboard import (
    ApplicationStatus,
    DashboardJobDetail,
    DashboardJobListResponse,
    DashboardStatusResponse,
    DashboardStatusUpdate,
)
from app.services.dashboard_service import DashboardJobService, DashboardPersistenceError


router = APIRouter()


@router.get("/jobs", response_model=DashboardJobListResponse)
def list_dashboard_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    keyword: Optional[str] = Query(None, max_length=200),
) -> DashboardJobListResponse:
    try:
        return DashboardJobService().list_jobs(
            page=page,
            page_size=page_size,
            status=status_filter,
            min_score=min_score,
            keyword=keyword,
        )
    except DashboardPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="岗位列表读取失败",
        ) from exc


@router.get("/jobs/{job_id}", response_model=DashboardJobDetail)
def get_dashboard_job(job_id: int) -> DashboardJobDetail:
    try:
        result = DashboardJobService().get_job(job_id)
    except DashboardPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="岗位详情读取失败",
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位不存在")
    return result


@router.patch("/jobs/{job_id}/status", response_model=DashboardStatusResponse)
def update_dashboard_job_status(
    job_id: int, payload: DashboardStatusUpdate
) -> DashboardStatusResponse:
    try:
        result = DashboardJobService().update_status(job_id, payload.status)
    except DashboardPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="投递状态更新失败",
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位不存在")
    return result
