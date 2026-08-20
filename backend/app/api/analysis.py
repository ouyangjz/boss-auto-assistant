from enum import IntEnum
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.analysis import AnalysisOverviewResponse
from app.schemas.dashboard import ApplicationStatus
from app.services.analysis_service import AnalysisPersistenceError, AnalysisService


router = APIRouter()


class AnalysisDays(IntEnum):
    LAST_7_DAYS = 7
    LAST_30_DAYS = 30


@router.get("/overview", response_model=AnalysisOverviewResponse)
def get_analysis_overview(
    days: Optional[AnalysisDays] = Query(None),
    job_category: Optional[str] = Query(None, max_length=255),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    application_status: Optional[ApplicationStatus] = Query(None),
) -> AnalysisOverviewResponse:
    try:
        return AnalysisService().overview(
            days=int(days) if days is not None else None,
            job_category=job_category,
            min_score=min_score,
            application_status=application_status,
        )
    except AnalysisPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="岗位分析数据读取失败",
        ) from exc
