from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Application,
    Base,
    EvaluationRequirement,
    Job,
    JobEvaluation,
)
from app.main import app
from app.services.analysis_service import AnalysisService


def _client_for(tmp_path, monkeypatch, name="analysis.db"):
    engine = create_engine(
        f"sqlite:///{(tmp_path / name).as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(
        "app.api.analysis.AnalysisService",
        lambda: AnalysisService(session_factory=sessions),
    )
    return TestClient(app), sessions


@pytest.fixture()
def analysis_database(tmp_path, monkeypatch):
    client, sessions = _client_for(tmp_path, monkeypatch)
    now = datetime.now().replace(microsecond=0)
    with sessions.begin() as session:
        jobs = [
            Job(job_id="analysis-1", job_name="后端一", created_at=now),
            Job(
                job_id="analysis-2",
                job_name="后端二",
                created_at=now - timedelta(days=2),
            ),
            Job(
                job_id="analysis-3",
                job_name="算法岗",
                created_at=now - timedelta(days=10),
            ),
            Job(job_id="analysis-4", job_name="待分析岗位", created_at=now),
        ]
        session.add_all(jobs)
        session.flush()
        evaluations = [
            JobEvaluation(
                job_id=jobs[0].id,
                match_score=88,
                job_category="Python 后端",
                self_intro_context=[{"matched_skills": ["Python", "Python"]}],
                raw_ai_output={},
            ),
            JobEvaluation(
                job_id=jobs[1].id,
                match_score=72,
                job_category="Python 后端",
                self_intro_context=[{"matched_skills": []}],
                raw_ai_output={},
            ),
            JobEvaluation(
                job_id=jobs[2].id,
                match_score=55,
                job_category="算法工程师",
                self_intro_context=None,
                raw_ai_output={},
            ),
        ]
        session.add_all(evaluations)
        session.flush()
        session.add_all(
            [
                EvaluationRequirement(
                    evaluation_id=evaluations[0].id,
                    requirement_type="required_skill",
                    content="Python",
                ),
                EvaluationRequirement(
                    evaluation_id=evaluations[0].id,
                    requirement_type="required_skill",
                    content=" python ",
                ),
                EvaluationRequirement(
                    evaluation_id=evaluations[0].id,
                    requirement_type="required_skill",
                    content="FastAPI",
                ),
                EvaluationRequirement(
                    evaluation_id=evaluations[0].id,
                    requirement_type="top_requirement",
                    content="熟悉 Python 开发",
                ),
                EvaluationRequirement(
                    evaluation_id=evaluations[0].id,
                    requirement_type="top_requirement",
                    content="熟悉 Python 开发",
                ),
                EvaluationRequirement(
                    evaluation_id=evaluations[1].id,
                    requirement_type="required_skill",
                    content="Python",
                ),
                EvaluationRequirement(
                    evaluation_id=evaluations[1].id,
                    requirement_type="required_skill",
                    content="Redis",
                ),
                EvaluationRequirement(
                    evaluation_id=evaluations[1].id,
                    requirement_type="top_requirement",
                    content="熟悉 Python 开发",
                ),
            ]
        )
        session.add_all(
            [
                Application(job_id=jobs[0].id, evaluation_id=evaluations[0].id, status="沟通"),
                Application(
                    job_id=jobs[2].id,
                    evaluation_id=evaluations[2].id,
                    status="面试阶段",
                ),
            ]
        )
    return client


def test_analysis_empty_database_returns_complete_empty_response(tmp_path, monkeypatch):
    client, _ = _client_for(tmp_path, monkeypatch, "empty-analysis.db")

    response = client.get("/api/v1/analysis/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total_jobs": 0,
        "average_match_score": None,
        "qualified_jobs": 0,
        "contacted_jobs": 0,
    }
    assert [item["count"] for item in body["match_score_distribution"]] == [0] * 6


def test_analysis_summary_distribution_and_dynamic_categories(analysis_database):
    response = analysis_database.get("/api/v1/analysis/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total_jobs": 4,
        "average_match_score": 71.7,
        "qualified_jobs": 2,
        "contacted_jobs": 2,
    }
    assert {item["range"]: item["count"] for item in body["match_score_distribution"]} == {
        "0-39": 0,
        "40-59": 1,
        "60-69": 0,
        "70-79": 1,
        "80-89": 1,
        "90-100": 0,
    }
    assert body["filter_options"]["job_categories"] == ["Python 后端", "算法工程师"]


def test_analysis_deduplicates_terms_per_job_and_builds_skill_comparisons(
    analysis_database,
):
    body = analysis_database.get("/api/v1/analysis/overview").json()

    assert body["top_required_skills"][0] == {
        "skill": "Python",
        "count": 2,
        "percentage": 50.0,
    }
    assert body["top_requirements"] == [
        {"requirement": "熟悉 Python 开发", "count": 2}
    ]
    assert body["strength_skills"] == [{"skill": "Python", "count": 1}]
    assert {item["skill"] for item in body["skill_gaps"]} == {
        "FastAPI",
        "Python",
        "Redis",
    }


@pytest.mark.parametrize(
    ("query", "expected_total"),
    [
        ("days=7", 3),
        ("job_category=Python%20后端", 2),
        ("min_score=80", 1),
        ("application_status=沟通", 1),
        ("application_status=未投递", 2),
    ],
)
def test_analysis_filters_apply_to_all_statistics(
    analysis_database, query, expected_total
):
    response = analysis_database.get(f"/api/v1/analysis/overview?{query}")

    assert response.status_code == 200
    assert response.json()["summary"]["total_jobs"] == expected_total


def test_analysis_limits_top_lists_to_ten_and_sorts_deterministically(
    tmp_path, monkeypatch
):
    client, sessions = _client_for(tmp_path, monkeypatch, "top-ten.db")
    with sessions.begin() as session:
        job = Job(job_id="top-ten", job_name="Top Ten")
        session.add(job)
        session.flush()
        evaluation = JobEvaluation(job_id=job.id, match_score=60, raw_ai_output={})
        session.add(evaluation)
        session.flush()
        session.add_all(
            EvaluationRequirement(
                evaluation_id=evaluation.id,
                requirement_type="required_skill",
                content=f"Skill-{index:02d}",
            )
            for index in range(12)
        )

    body = client.get("/api/v1/analysis/overview").json()

    assert len(body["top_required_skills"]) == 10
    assert [item["skill"] for item in body["top_required_skills"]] == [
        f"Skill-{index:02d}" for index in range(10)
    ]


def test_analysis_tolerates_empty_and_invalid_historical_json(tmp_path, monkeypatch):
    client, sessions = _client_for(tmp_path, monkeypatch, "invalid-json.db")
    with sessions.begin() as session:
        job = Job(job_id="invalid-json", job_name="历史数据")
        session.add(job)
        session.flush()
        session.add(
            JobEvaluation(
                job_id=job.id,
                match_score=None,
                self_intro_context="not-json",
                raw_ai_output={},
            )
        )

    response = client.get("/api/v1/analysis/overview")

    assert response.status_code == 200
    assert response.json()["strength_skills"] == []
    assert response.json()["skill_gaps"] == []


def test_analysis_rejects_unsupported_filter_values(analysis_database):
    assert analysis_database.get("/api/v1/analysis/overview?days=14").status_code == 422
    assert analysis_database.get("/api/v1/analysis/overview?min_score=101").status_code == 422
    assert (
        analysis_database.get(
            "/api/v1/analysis/overview?application_status=不存在"
        ).status_code
        == 422
    )
