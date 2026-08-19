from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database.models import Application, Job, JobEvaluation


@dataclass(frozen=True)
class DashboardJobRow:
    job: Job
    evaluation: Optional[JobEvaluation]
    application: Optional[Application]


class DashboardJobRepository:
    """Dashboard-only queries kept separate from the automated evaluation flow."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _latest_evaluation_ids():
        return (
            select(
                JobEvaluation.job_id.label("job_id"),
                func.max(JobEvaluation.id).label("evaluation_id"),
            )
            .group_by(JobEvaluation.job_id)
            .subquery()
        )

    def _list_statement(
        self,
        *,
        status: Optional[str],
        min_score: Optional[int],
        keyword: Optional[str],
    ) -> Select:
        latest = self._latest_evaluation_ids()
        statement = (
            select(Job, JobEvaluation, Application)
            .outerjoin(latest, latest.c.job_id == Job.id)
            .outerjoin(JobEvaluation, JobEvaluation.id == latest.c.evaluation_id)
            .outerjoin(Application, Application.job_id == Job.id)
        )
        if status:
            if status == "未投递":
                statement = statement.where(
                    or_(Application.status == status, Application.id.is_(None))
                )
            else:
                statement = statement.where(Application.status == status)
        if min_score is not None:
            statement = statement.where(JobEvaluation.match_score >= min_score)
        normalized_keyword = (keyword or "").strip()
        if normalized_keyword:
            escaped = (
                normalized_keyword.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(
                    Job.job_name.ilike(pattern, escape="\\"),
                    Job.company_name.ilike(pattern, escape="\\"),
                )
            )
        return statement

    def list_jobs(
        self,
        *,
        page: int,
        page_size: int,
        status: Optional[str],
        min_score: Optional[int],
        keyword: Optional[str],
    ) -> Tuple[Sequence[DashboardJobRow], int]:
        statement = self._list_statement(
            status=status, min_score=min_score, keyword=keyword
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.subquery())
        ) or 0
        rows = self.session.execute(
            statement.order_by(Job.created_at.desc(), Job.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [DashboardJobRow(*row) for row in rows], total

    def get_job(self, job_id: int) -> Optional[DashboardJobRow]:
        job = self.session.scalar(
            select(Job)
            .options(selectinload(Job.tags))
            .where(Job.id == job_id)
        )
        if job is None:
            return None
        evaluation = self.session.scalar(
            select(JobEvaluation)
            .options(selectinload(JobEvaluation.requirements))
            .where(JobEvaluation.job_id == job_id)
            .order_by(JobEvaluation.id.desc())
            .limit(1)
        )
        application = self.session.scalar(
            select(Application)
            .options(selectinload(Application.communication))
            .where(Application.job_id == job_id)
        )
        return DashboardJobRow(job, evaluation, application)

    def update_status(self, job_id: int, status: str) -> Optional[Application]:
        job = self.session.get(Job, job_id)
        if job is None:
            return None
        application = self.session.scalar(
            select(Application).where(Application.job_id == job_id)
        )
        if application is None:
            application = Application(job_id=job_id, status=status)
            self.session.add(application)
        else:
            application.status = status
        self.session.flush()
        return application
