from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database.analysis_repository import AnalysisJobRow, AnalysisRepository
from app.database.connection import SessionLocal
from app.schemas.analysis import (
    AnalysisFilterOptions,
    AnalysisOverviewResponse,
    AnalysisSummary,
    JobCategoryCount,
    MatchScoreBucket,
    RequirementFrequency,
    SkillCount,
    SkillFrequency,
)
from app.schemas.dashboard import ApplicationStatus


logger = logging.getLogger(__name__)


class AnalysisPersistenceError(OSError):
    pass


SCORE_BUCKETS: Tuple[Tuple[str, int, int], ...] = (
    ("0-39", 0, 39),
    ("40-59", 40, 59),
    ("60-69", 60, 69),
    ("70-79", 70, 79),
    ("80-89", 80, 89),
    ("90-100", 90, 100),
)


def _deduplicated_terms(values: Iterable[Any]) -> dict[str, str]:
    terms: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str):
            continue
        display = value.strip()
        if display:
            terms.setdefault(display.casefold(), display)
    return terms


def _decode_json_container(value: Any, field_name: str) -> Any:
    if not isinstance(value, str):
        return value
    if not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        logger.warning("Skip invalid JSON in analysis field %s", field_name)
        return None


def _matched_skills(value: Any) -> Optional[dict[str, str]]:
    """Return None when matched_skills is absent, preserving honest empty states."""
    container = _decode_json_container(value, "self_intro_context")
    items: Sequence[Any]
    if isinstance(container, dict):
        items = [container]
    elif isinstance(container, list):
        items = container
    else:
        return None

    found = False
    values: list[Any] = []
    for item in items:
        if not isinstance(item, dict) or "matched_skills" not in item:
            continue
        found = True
        matched = _decode_json_container(item.get("matched_skills"), "matched_skills")
        if isinstance(matched, list):
            values.extend(matched)
        elif matched not in (None, ""):
            logger.warning("Skip non-array matched_skills in analysis data")
            return None
    return _deduplicated_terms(values) if found else None


def _sorted_counter(counter: Counter[str], labels: dict[str, str], limit: int):
    return sorted(
        ((labels[key], count) for key, count in counter.items()),
        key=lambda item: (-item[1], item[0].casefold()),
    )[:limit]


class AnalysisService:
    def __init__(self, session_factory: sessionmaker = SessionLocal):
        self.session_factory = session_factory

    def overview(
        self,
        *,
        days: Optional[int],
        job_category: Optional[str],
        min_score: Optional[int],
        application_status: Optional[ApplicationStatus],
        now: Optional[datetime] = None,
    ) -> AnalysisOverviewResponse:
        try:
            with self.session_factory() as session:
                repository = AnalysisRepository(session)
                rows = repository.list_jobs(
                    days=days,
                    job_category=(job_category or "").strip() or None,
                    min_score=min_score,
                    application_status=(
                        application_status.value if application_status else None
                    ),
                    now=now or datetime.now(),
                )
                categories = repository.list_categories()
        except SQLAlchemyError as exc:
            raise AnalysisPersistenceError(str(exc)) from exc

        return self._build_response(rows, categories)

    @staticmethod
    def _build_response(
        rows: Sequence[AnalysisJobRow], categories: Sequence[str]
    ) -> AnalysisOverviewResponse:
        valid_scores = [
            row.match_score
            for row in rows
            if isinstance(row.match_score, (int, float))
            and not isinstance(row.match_score, bool)
            and 0 <= row.match_score <= 100
        ]
        average_score = (
            round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None
        )
        contacted_statuses = {
            status.value
            for status in ApplicationStatus
            if status is not ApplicationStatus.NOT_APPLIED
        }

        buckets = {label: 0 for label, _, _ in SCORE_BUCKETS}
        for score in valid_scores:
            for label, lower, upper in SCORE_BUCKETS:
                if lower <= score <= upper:
                    buckets[label] += 1
                    break

        category_counter: Counter[str] = Counter()
        category_labels: dict[str, str] = {}
        required_counter: Counter[str] = Counter()
        required_labels: dict[str, str] = {}
        requirement_counter: Counter[str] = Counter()
        requirement_labels: dict[str, str] = {}
        matched_counter: Counter[str] = Counter()
        matched_labels: dict[str, str] = {}
        gap_counter: Counter[str] = Counter()
        gap_labels: dict[str, str] = {}
        matched_data_available = False

        for row in rows:
            if row.job_category.strip():
                key = row.job_category.strip().casefold()
                category_labels.setdefault(key, row.job_category.strip())
                category_counter[key] += 1

            required = _deduplicated_terms(
                requirement.content
                for requirement in row.requirements
                if requirement.requirement_type == "required_skill"
            )
            top_requirements = _deduplicated_terms(
                requirement.content
                for requirement in row.requirements
                if requirement.requirement_type == "top_requirement"
            )
            for key, label in required.items():
                required_labels.setdefault(key, label)
                required_counter[key] += 1
            for key, label in top_requirements.items():
                requirement_labels.setdefault(key, label)
                requirement_counter[key] += 1

            matched = _matched_skills(row.self_intro_context)
            if matched is None:
                continue
            matched_data_available = True
            for key, label in matched.items():
                matched_labels.setdefault(key, label)
                matched_counter[key] += 1
            for key in required.keys() - matched.keys():
                gap_labels.setdefault(key, required[key])
                gap_counter[key] += 1

        total_jobs = len(rows)
        top_required = _sorted_counter(required_counter, required_labels, 10)
        top_requirement_rows = _sorted_counter(
            requirement_counter, requirement_labels, 10
        )
        category_rows = _sorted_counter(category_counter, category_labels, 10)
        strengths = (
            _sorted_counter(matched_counter, matched_labels, 5)
            if matched_data_available
            else []
        )
        gaps = (
            _sorted_counter(gap_counter, gap_labels, 5)
            if matched_data_available
            else []
        )

        return AnalysisOverviewResponse(
            summary=AnalysisSummary(
                total_jobs=total_jobs,
                average_match_score=average_score,
                qualified_jobs=sum(score >= 70 for score in valid_scores),
                contacted_jobs=sum(
                    row.application_status in contacted_statuses for row in rows
                ),
            ),
            match_score_distribution=[
                MatchScoreBucket(range=label, count=buckets[label])
                for label, _, _ in SCORE_BUCKETS
            ],
            job_category_distribution=[
                JobCategoryCount(category=label, count=count)
                for label, count in category_rows
            ],
            top_required_skills=[
                SkillFrequency(
                    skill=label,
                    count=count,
                    percentage=round(count / total_jobs * 100, 1)
                    if total_jobs
                    else 0.0,
                )
                for label, count in top_required
            ],
            top_requirements=[
                RequirementFrequency(requirement=label, count=count)
                for label, count in top_requirement_rows
            ],
            strength_skills=[
                SkillCount(skill=label, count=count) for label, count in strengths
            ],
            skill_gaps=[SkillCount(skill=label, count=count) for label, count in gaps],
            filter_options=AnalysisFilterOptions(
                job_categories=list(categories),
                application_statuses=list(ApplicationStatus),
            ),
        )
