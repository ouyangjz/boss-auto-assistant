from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database.models import Application, EvaluationRequirement, Job, JobEvaluation


@dataclass(frozen=True)
class AnalysisRequirementRow:
    requirement_type: str
    content: str


@dataclass(frozen=True)
class AnalysisJobRow:
    job_id: int
    created_at: datetime
    match_score: Optional[int]
    job_category: str
    application_status: Optional[str]
    self_intro_context: Any
    requirements: Sequence[AnalysisRequirementRow]


class AnalysisRepository:
    """Read-only queries used by the job analysis page."""

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

    def list_jobs(
        self,
        *,
        days: Optional[int],
        job_category: Optional[str],
        min_score: Optional[int],
        application_status: Optional[str],
        now: datetime,
    ) -> Sequence[AnalysisJobRow]:
        latest = self._latest_evaluation_ids()
        statement = (
            select(
                Job.id,
                Job.created_at,
                JobEvaluation.id,
                JobEvaluation.match_score,
                JobEvaluation.job_category,
                Application.status,
                JobEvaluation.self_intro_context,
            )
            .outerjoin(latest, latest.c.job_id == Job.id)
            .outerjoin(JobEvaluation, JobEvaluation.id == latest.c.evaluation_id)
            .outerjoin(Application, Application.job_id == Job.id)
        )
        if days is not None:
            statement = statement.where(Job.created_at >= now - timedelta(days=days))
        if job_category:
            statement = statement.where(JobEvaluation.job_category == job_category)
        if min_score is not None:
            statement = statement.where(JobEvaluation.match_score >= min_score)
        if application_status:
            if application_status == "未投递":
                statement = statement.where(
                    or_(Application.status == application_status, Application.id.is_(None))
                )
            else:
                statement = statement.where(Application.status == application_status)

        raw_rows = self.session.execute(statement.order_by(Job.id)).all()
        evaluation_ids = [row[2] for row in raw_rows if row[2] is not None]
        requirements: dict[int, list[AnalysisRequirementRow]] = {}
        if evaluation_ids:
            requirement_rows = self.session.execute(
                select(
                    EvaluationRequirement.evaluation_id,
                    EvaluationRequirement.requirement_type,
                    EvaluationRequirement.content,
                ).where(EvaluationRequirement.evaluation_id.in_(evaluation_ids))
            ).all()
            for evaluation_id, requirement_type, content in requirement_rows:
                requirements.setdefault(evaluation_id, []).append(
                    AnalysisRequirementRow(
                        requirement_type=requirement_type,
                        content=content,
                    )
                )

        return [
            AnalysisJobRow(
                job_id=row[0],
                created_at=row[1],
                match_score=row[3],
                job_category=row[4] or "",
                application_status=row[5],
                self_intro_context=row[6],
                requirements=requirements.get(row[2], ()),
            )
            for row in raw_rows
        ]

    def list_categories(self) -> Tuple[str, ...]:
        latest = self._latest_evaluation_ids()
        values = self.session.scalars(
            select(JobEvaluation.job_category)
            .join(latest, JobEvaluation.id == latest.c.evaluation_id)
            .where(JobEvaluation.job_category != "")
            .distinct()
            .order_by(JobEvaluation.job_category)
        ).all()
        return tuple(value.strip() for value in values if value and value.strip())
