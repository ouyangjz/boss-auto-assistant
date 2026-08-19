import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database.connection import SessionLocal
from app.database.models import Application
from app.database.repositories import (
    ApplicationRepository,
    CommunicationRepository,
    EvaluationRepository,
    JobRepository,
)


class DatabasePersistenceError(OSError):
    """Keep the API's existing persistence-error handling contract."""


@dataclass(frozen=True)
class SaveJobResult:
    job_database_id: int
    evaluation_database_id: Optional[int]
    application_database_id: Optional[int]
    job_created: bool
    evaluation_created: bool


@dataclass(frozen=True)
class SaveCommunicationResult:
    communication_database_id: int
    created: bool


APPLICATION_STATUSES = (
    "未投递",
    "沟通",
    "投递简历",
    "面试阶段",
    "入职阶段",
)


JOB_FIELDS = (
    "job_name",
    "salary",
    "location",
    "experience",
    "education",
    "company_name",
    "hr_name",
    "hr_title",
    "job_description",
    "source_url",
)


def _string(value: Any) -> str:
    return "" if value is None else str(value)


def _json_safe(value: Any, field_name: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not JSON serializable: {exc}") from exc
    return value


def _business_job_id(payload: Dict[str, Any]) -> str:
    job_id = _string(payload.get("job_id")).strip()
    if job_id:
        return job_id
    fallback_fields = {name: payload.get(name) for name in JOB_FIELDS}
    canonical = json.dumps(fallback_fields, ensure_ascii=False, sort_keys=True, default=str)
    return "missing:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def job_exists(
    job_id: str,
    *,
    session_factory: sessionmaker = SessionLocal,
) -> bool:
    """Return whether a non-empty business job ID is already persisted."""
    normalized_job_id = _string(job_id).strip()
    if not normalized_job_id:
        return False

    try:
        with session_factory() as session:
            return JobRepository(session).get_by_business_id(normalized_job_id) is not None
    except SQLAlchemyError as exc:
        raise DatabasePersistenceError(str(exc)) from exc


def _match_score(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("match_score must be an integer between 0 and 100")
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("match_score must be an integer between 0 and 100") from exc
    if not 0 <= score <= 100:
        raise ValueError("match_score must be between 0 and 100")
    return score


def _array(value: Any, field_name: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return value


def _requirement_rows(
    coze_output: Dict[str, Any], created_at: datetime
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in _array(coze_output.get("top_requirements"), "top_requirements"):
        if isinstance(item, dict):
            content = _string(item.get("requirement") or item.get("content")).strip()
            if content:
                importance = item.get("importance")
                rows.append(
                    {
                        "requirement_type": "top_requirement",
                        "content": content,
                        "importance": int(importance) if importance not in (None, "") else None,
                        "logic": _string(item.get("logic")).strip() or None,
                        "alternatives": _json_safe(
                            item.get("alternatives") or [], "alternatives"
                        ),
                        "created_at": created_at,
                    }
                )
        else:
            content = _string(item).strip()
            if content:
                rows.append(
                    {
                        "requirement_type": "top_requirement",
                        "content": content,
                        "importance": None,
                        "logic": None,
                        "alternatives": [],
                        "created_at": created_at,
                    }
                )

    for source_name, requirement_type in (
        ("required_skills", "required_skill"),
        ("preferred_skills", "preferred_skill"),
    ):
        for item in _array(coze_output.get(source_name), source_name):
            content = _string(
                item.get("requirement") if isinstance(item, dict) else item
            ).strip()
            if content:
                rows.append(
                    {
                        "requirement_type": requirement_type,
                        "content": content,
                        "importance": None,
                        "logic": None,
                        "alternatives": None,
                        "created_at": created_at,
                    }
                )
    return rows


def save_job_result(
    payload: Dict[str, Any],
    *,
    source_file: Optional[str] = None,
    migration_key: Optional[str] = None,
    created_at: Optional[datetime] = None,
    application_status: Optional[str] = None,
    session_factory: sessionmaker = SessionLocal,
) -> SaveJobResult:
    """Persist one job and its optional evaluation atomically."""
    timestamp = created_at or datetime.now()
    coze_output = payload.get("coze_output")
    if coze_output is not None and not isinstance(coze_output, dict):
        raise ValueError("coze_output must be an object")
    if application_status is not None and application_status not in APPLICATION_STATUSES:
        raise ValueError(f"unsupported application status: {application_status}")
    if application_status is not None and coze_output is None:
        raise ValueError("an application status requires an evaluation")

    try:
        with session_factory.begin() as session:
            jobs = JobRepository(session)
            evaluations = EvaluationRepository(session)

            if migration_key:
                existing_evaluation = evaluations.get_by_migration_key(migration_key)
                if existing_evaluation is not None:
                    return SaveJobResult(
                        job_database_id=existing_evaluation.job_id,
                        evaluation_database_id=existing_evaluation.id,
                        application_database_id=None,
                        job_created=False,
                        evaluation_created=False,
                    )

            business_job_id = _business_job_id(payload)
            job = jobs.get_by_business_id(business_job_id)
            job_values = {name: _string(payload.get(name)) for name in JOB_FIELDS}
            if job is None:
                job = jobs.create(
                    {
                        "job_id": business_job_id,
                        **job_values,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                )
                job_created = True
            else:
                update_values = {
                    name: _string(payload.get(name))
                    for name in JOB_FIELDS
                    if name in payload
                }
                jobs.update(job, {**update_values, "updated_at": timestamp})
                job_created = False

            if "job_tags" in payload:
                raw_tags = _array(payload.get("job_tags"), "job_tags")
                jobs.sync_tags(job, (_string(tag) for tag in raw_tags), timestamp)

            evaluation = None
            application = None
            if coze_output is not None:
                evaluation = evaluations.create(
                    job,
                    {
                        "match_score": _match_score(coze_output.get("match_score")),
                        "job_category": _string(coze_output.get("job_category")),
                        "summary": _string(coze_output.get("summary")),
                        "query": _string(coze_output.get("query")),
                        "output_list": _json_safe(
                            coze_output.get("outputList") or [], "outputList"
                        ),
                        "self_intro_context": _json_safe(
                            coze_output.get("self_intro_context") or [],
                            "self_intro_context",
                        ),
                        "raw_ai_output": _json_safe(coze_output, "coze_output"),
                        "source_file": source_file,
                        "migration_key": migration_key,
                        "created_at": timestamp,
                    },
                    _requirement_rows(coze_output, timestamp),
                )
                if application_status is not None:
                    application = ApplicationRepository(
                        session
                    ).create_or_update_from_evaluation(
                        job,
                        evaluation,
                        application_status,
                        timestamp,
                    )

            return SaveJobResult(
                job_database_id=job.id,
                evaluation_database_id=evaluation.id if evaluation else None,
                application_database_id=application.id if application else None,
                job_created=job_created,
                evaluation_created=evaluation is not None,
            )
    except SQLAlchemyError as exc:
        raise DatabasePersistenceError(str(exc)) from exc


def save_first_communication(
    application_id: int,
    content: str,
    *,
    created_at: Optional[datetime] = None,
    session_factory: sessionmaker = SessionLocal,
) -> SaveCommunicationResult:
    """Save the generated greeting once and never overwrite the first one."""
    normalized_content = str(content).strip()
    if not normalized_content:
        raise ValueError("communication content cannot be empty")

    try:
        with session_factory.begin() as session:
            if session.get(Application, application_id) is None:
                raise ValueError(f"application does not exist: {application_id}")
            communications = CommunicationRepository(session)
            existing = communications.get_by_application_id(application_id)
            if existing is not None:
                return SaveCommunicationResult(existing.id, created=False)
            communication = communications.create_first(
                application_id,
                normalized_content,
                created_at or datetime.now(),
            )
            return SaveCommunicationResult(communication.id, created=True)
    except SQLAlchemyError as exc:
        raise DatabasePersistenceError(str(exc)) from exc
