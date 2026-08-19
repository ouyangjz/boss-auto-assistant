from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    Application,
    Communication,
    EvaluationRequirement,
    Job,
    JobEvaluation,
    JobTag,
)


class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_business_id(self, job_id: str) -> Optional[Job]:
        return self.session.scalar(select(Job).where(Job.job_id == job_id))

    def create(self, values: Dict[str, Any]) -> Job:
        job = Job(**values)
        self.session.add(job)
        self.session.flush()
        return job

    def update(self, job: Job, values: Dict[str, Any]) -> None:
        for name, value in values.items():
            setattr(job, name, value)

    def sync_tags(self, job: Job, tags: Iterable[str], created_at: datetime) -> None:
        normalized = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
        existing = {tag.tag: tag for tag in job.tags}
        for value, tag in existing.items():
            if value not in normalized:
                self.session.delete(tag)
        for value in normalized:
            if value not in existing:
                self.session.add(JobTag(job=job, tag=value, created_at=created_at))


class EvaluationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_migration_key(self, migration_key: str) -> Optional[JobEvaluation]:
        return self.session.scalar(
            select(JobEvaluation).where(JobEvaluation.migration_key == migration_key)
        )

    def create(
        self,
        job: Job,
        values: Dict[str, Any],
        requirements: Iterable[Dict[str, Any]],
    ) -> JobEvaluation:
        evaluation = JobEvaluation(job=job, **values)
        self.session.add(evaluation)
        self.session.flush()
        for requirement in requirements:
            self.session.add(
                EvaluationRequirement(evaluation=evaluation, **requirement)
            )
        self.session.flush()
        return evaluation


class ApplicationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_job_id(self, job_id: int) -> Optional[Application]:
        return self.session.scalar(
            select(Application).where(Application.job_id == job_id)
        )

    def create_or_update_from_evaluation(
        self,
        job: Job,
        evaluation: JobEvaluation,
        status: str,
        timestamp: datetime,
    ) -> Application:
        application = self.get_by_job_id(job.id)
        if application is None:
            application = Application(
                job=job,
                evaluation=evaluation,
                status=status,
                created_at=timestamp,
                updated_at=timestamp,
            )
            self.session.add(application)
        else:
            application.evaluation = evaluation
            if application.status in ("未投递", "沟通"):
                application.status = status
            application.updated_at = timestamp
        self.session.flush()
        return application


class CommunicationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_application_id(self, application_id: int) -> Optional[Communication]:
        return self.session.scalar(
            select(Communication).where(
                Communication.application_id == application_id
            )
        )

    def create_first(
        self, application_id: int, content: str, timestamp: datetime
    ) -> Communication:
        communication = Communication(
            application_id=application_id,
            content=content,
            created_at=timestamp,
        )
        self.session.add(communication)
        self.session.flush()
        return communication
