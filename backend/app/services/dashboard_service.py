from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database.connection import SessionLocal
from app.database.dashboard_repository import DashboardJobRepository, DashboardJobRow
from app.schemas.dashboard import (
    ApplicationStatus,
    DashboardJobDetail,
    DashboardJobItem,
    DashboardJobListResponse,
    DashboardRequirement,
    DashboardStatusResponse,
)


class DashboardPersistenceError(OSError):
    pass


class DashboardJobService:
    def __init__(self, session_factory: sessionmaker = SessionLocal):
        self.session_factory = session_factory

    @staticmethod
    def _status(row: DashboardJobRow) -> ApplicationStatus:
        value = row.application.status if row.application else ApplicationStatus.NOT_APPLIED
        return ApplicationStatus(value)

    @classmethod
    def _item(cls, row: DashboardJobRow) -> DashboardJobItem:
        return DashboardJobItem(
            id=row.job.id,
            job_id=row.job.job_id,
            job_name=row.job.job_name,
            company_name=row.job.company_name,
            hr_name=row.job.hr_name,
            hr_title=row.job.hr_title,
            match_score=row.evaluation.match_score if row.evaluation else None,
            status=cls._status(row),
            created_at=row.job.created_at,
        )

    @staticmethod
    def _model_data(model: DashboardJobItem) -> Dict[str, Any]:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    def list_jobs(
        self,
        *,
        page: int,
        page_size: int,
        status: Optional[ApplicationStatus],
        min_score: Optional[int],
        keyword: Optional[str],
    ) -> DashboardJobListResponse:
        try:
            with self.session_factory() as session:
                rows, total = DashboardJobRepository(session).list_jobs(
                    page=page,
                    page_size=page_size,
                    status=status.value if status else None,
                    min_score=min_score,
                    keyword=keyword,
                )
                return DashboardJobListResponse(
                    items=[self._item(row) for row in rows],
                    page=page,
                    page_size=page_size,
                    total=total,
                )
        except SQLAlchemyError as exc:
            raise DashboardPersistenceError(str(exc)) from exc

    def get_job(self, job_id: int) -> Optional[DashboardJobDetail]:
        try:
            with self.session_factory() as session:
                row = DashboardJobRepository(session).get_job(job_id)
                if row is None:
                    return None
                evaluation = row.evaluation
                grouped: Dict[str, list[Any]] = {
                    "required_skill": [],
                    "preferred_skill": [],
                    "top_requirement": [],
                }
                if evaluation:
                    for requirement in evaluation.requirements:
                        if requirement.requirement_type == "top_requirement":
                            grouped["top_requirement"].append(
                                DashboardRequirement(
                                    content=requirement.content,
                                    importance=requirement.importance,
                                    logic=requirement.logic,
                                    alternatives=requirement.alternatives,
                                )
                            )
                        elif requirement.requirement_type in grouped:
                            grouped[requirement.requirement_type].append(
                                requirement.content
                            )
                communication = (
                    row.application.communication if row.application else None
                )
                return DashboardJobDetail(
                    **self._model_data(self._item(row)),
                    salary=row.job.salary,
                    location=row.job.location,
                    experience=row.job.experience,
                    education=row.job.education,
                    job_description=row.job.job_description,
                    source_url=row.job.source_url,
                    tags=[tag.tag for tag in row.job.tags],
                    updated_at=row.job.updated_at,
                    job_category=evaluation.job_category if evaluation else "",
                    summary=evaluation.summary if evaluation else "",
                    required_skills=grouped["required_skill"],
                    preferred_skills=grouped["preferred_skill"],
                    top_requirements=grouped["top_requirement"],
                    self_intro_context=(
                        evaluation.self_intro_context if evaluation else None
                    ),
                    generated_introduction=(
                        communication.content if communication else None
                    ),
                )
        except SQLAlchemyError as exc:
            raise DashboardPersistenceError(str(exc)) from exc

    def update_status(
        self, job_id: int, status: ApplicationStatus
    ) -> Optional[DashboardStatusResponse]:
        try:
            with self.session_factory.begin() as session:
                application = DashboardJobRepository(session).update_status(
                    job_id, status.value
                )
                if application is None:
                    return None
                return DashboardStatusResponse(id=job_id, status=status)
        except SQLAlchemyError as exc:
            raise DashboardPersistenceError(str(exc)) from exc
