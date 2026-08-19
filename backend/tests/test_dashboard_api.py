from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Application,
    Base,
    Communication,
    EvaluationRequirement,
    Job,
    JobEvaluation,
    JobTag,
)
from app.main import app
from app.services.dashboard_service import DashboardJobService


@pytest.fixture()
def dashboard_database(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'dashboard.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 19, 10, 0, 0)
    with sessions.begin() as session:
        first = Job(
            job_id="boss-1",
            job_name="Python 后端工程师",
            company_name="示例科技",
            hr_name="张先生",
            hr_title="招聘经理",
            job_description="第一行\n第二行",
            salary="20-30K",
            location="深圳",
            experience="3-5年",
            education="本科",
            source_url="https://example.com/1",
            created_at=now,
            updated_at=now,
        )
        second = Job(
            job_id="boss-2",
            job_name="产品经理",
            company_name="另一家公司",
            created_at=now - timedelta(days=1),
            updated_at=now,
        )
        third = Job(
            job_id="boss-3",
            job_name="Python 数据工程师",
            company_name="数据公司",
            created_at=now - timedelta(days=2),
            updated_at=now,
        )
        session.add_all([first, second, third])
        session.flush()
        session.add(JobTag(job_id=first.id, tag="Python", created_at=now))
        older_evaluation = JobEvaluation(
            job_id=first.id,
            match_score=60,
            raw_ai_output={},
            created_at=now - timedelta(hours=1),
        )
        latest_evaluation = JobEvaluation(
            job_id=first.id,
            match_score=88,
            job_category="后端开发",
            summary="匹配良好",
            self_intro_context=[{"matched_skills": ["Python"]}],
            raw_ai_output={},
            created_at=now,
        )
        third_evaluation = JobEvaluation(
            job_id=third.id,
            match_score=72,
            raw_ai_output={},
            created_at=now,
        )
        session.add_all([older_evaluation, latest_evaluation, third_evaluation])
        session.flush()
        session.add_all(
            [
                EvaluationRequirement(
                    evaluation_id=latest_evaluation.id,
                    requirement_type="required_skill",
                    content="Python",
                    created_at=now,
                ),
                EvaluationRequirement(
                    evaluation_id=latest_evaluation.id,
                    requirement_type="top_requirement",
                    content="熟悉 FastAPI",
                    importance=10,
                    created_at=now,
                ),
            ]
        )
        application = Application(
            job_id=first.id,
            evaluation_id=latest_evaluation.id,
            status="沟通",
            created_at=now,
            updated_at=now,
        )
        session.add(application)
        session.flush()
        session.add(
            Communication(
                application_id=application.id,
                content="您好，我有 Python 项目经验。",
                created_at=now,
            )
        )

    monkeypatch.setattr(
        "app.api.dashboard.DashboardJobService",
        lambda: DashboardJobService(session_factory=sessions),
    )
    return TestClient(app), sessions


def test_dashboard_list_uses_latest_evaluation_and_paginates(dashboard_database):
    client, _ = dashboard_database
    response = client.get("/api/v1/dashboard/jobs?page=1&page_size=2")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [1, 2]
    assert body["items"][0]["match_score"] == 88
    assert body["items"][1]["status"] == "未投递"


@pytest.mark.parametrize(
    ("query", "expected_ids"),
    [
        ("status=沟通", [1]),
        ("status=未投递", [2, 3]),
        ("min_score=80", [1]),
        ("keyword=Python", [1, 3]),
        ("keyword=示例科技", [1]),
    ],
)
def test_dashboard_list_filters(dashboard_database, query, expected_ids):
    client, _ = dashboard_database
    response = client.get(f"/api/v1/dashboard/jobs?{query}")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == expected_ids


def test_dashboard_detail_returns_structured_existing_data(dashboard_database):
    client, _ = dashboard_database
    response = client.get("/api/v1/dashboard/jobs/1")

    assert response.status_code == 200
    body = response.json()
    assert body["job_description"] == "第一行\n第二行"
    assert body["tags"] == ["Python"]
    assert body["required_skills"] == ["Python"]
    assert body["top_requirements"][0]["content"] == "熟悉 FastAPI"
    assert body["self_intro_context"][0]["matched_skills"] == ["Python"]
    assert body["generated_introduction"] == "您好，我有 Python 项目经验。"


def test_dashboard_detail_returns_404(dashboard_database):
    client, _ = dashboard_database
    response = client.get("/api/v1/dashboard/jobs/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "岗位不存在"}


def test_dashboard_status_update_persists(dashboard_database):
    client, _ = dashboard_database
    response = client.patch(
        "/api/v1/dashboard/jobs/1/status", json={"status": "面试阶段"}
    )

    assert response.status_code == 200
    assert response.json() == {"id": 1, "status": "面试阶段"}
    refreshed = client.get("/api/v1/dashboard/jobs/1")
    assert refreshed.json()["status"] == "面试阶段"


def test_dashboard_status_update_creates_missing_application(dashboard_database):
    client, _ = dashboard_database
    response = client.patch(
        "/api/v1/dashboard/jobs/2/status", json={"status": "投递简历"}
    )

    assert response.status_code == 200
    assert client.get("/api/v1/dashboard/jobs/2").json()["status"] == "投递简历"


def test_dashboard_status_update_rejects_invalid_status(dashboard_database):
    client, _ = dashboard_database
    response = client.patch(
        "/api/v1/dashboard/jobs/1/status", json={"status": "invalid"}
    )

    assert response.status_code == 422
    assert client.get("/api/v1/dashboard/jobs/1").json()["status"] == "沟通"


def test_dashboard_status_update_returns_404(dashboard_database):
    client, _ = dashboard_database
    response = client.patch(
        "/api/v1/dashboard/jobs/999/status", json={"status": "未投递"}
    )

    assert response.status_code == 404
