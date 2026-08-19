from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import Application, Base, Communication
from app.database.services import (
    save_first_communication as database_save_first_communication,
)
from app.database.services import save_job_result as database_save_job_result
from app.main import app
from app.services.coze_client import CozeResponseError, CozeTimeoutError


client = TestClient(app)


@pytest.fixture(autouse=True)
def persisted_payloads(monkeypatch):
    class PersistenceCalls(list):
        application_statuses = []

    payloads = PersistenceCalls()

    def fake_save_job_result(payload, **kwargs):
        payloads.append(payload)
        payloads.application_statuses.append(kwargs.get("application_status"))
        return SimpleNamespace(
            job_database_id=1,
            evaluation_database_id=len(payloads),
            application_database_id=42,
        )

    monkeypatch.setattr(
        "app.services.job_service.save_job_result", fake_save_job_result
    )
    monkeypatch.setattr("app.services.job_service.job_exists", lambda _job_id: False)
    return payloads


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_evaluate_returns_coze_score_and_saves_complete_output(
    monkeypatch, tmp_path, persisted_payloads
):
    received = {}

    async def fake_run_job_evaluation(**kwargs):
        received.update(kwargs)
        return {
            "job_category": "AI智能体开发",
            "match_score": 83,
            "outputList": [{"name": "Python"}],
            "summary": "匹配",
        }

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path, match_threshold=70),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )
    response = client.post(
        "/api/v1/jobs/evaluate",
        json={
            "job_id": "abc",
            "job_name": "AI Agent 工程师",
            "salary": "10-15K",
            "job_description": "第一行\n第二行",
            "job_tags": ["Python", "Agent"],
            "company_name": "示例公司",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 83}
    assert received == {
        "job_name": "AI Agent 工程师",
        "job_description": "第一行\n第二行",
        "job_tags": ["Python", "Agent"],
    }
    assert len(persisted_payloads) == 1
    saved = persisted_payloads[0]
    assert saved["job_id"] == "abc"
    assert saved["salary"] == "10-15K"
    assert saved["company_name"] == "示例公司"
    assert saved["job_description"] == "第一行\n第二行"
    assert saved["job_tags"] == ["Python", "Agent"]
    assert saved["coze_output"] == {
        "job_category": "AI智能体开发",
        "match_score": 83,
        "outputList": [{"name": "Python"}],
        "summary": "匹配",
    }
    assert "location" not in saved
    assert persisted_payloads.application_statuses == ["沟通"]


def test_blacklisted_job_returns_zero_without_calling_coze_or_saving(
    monkeypatch, tmp_path, persisted_payloads
):
    async def fail_if_called(**kwargs):
        raise AssertionError("blacklisted job must not call Coze")

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path, match_threshold=70),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fail_if_called,
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={
            "job_id": "blacklisted-job",
            "job_name": "亚马逊英语客服（双休）",
            "job_tags": ["线上客服"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 0}
    assert persisted_payloads == []


def test_existing_job_returns_zero_without_calling_coze_or_saving(
    monkeypatch, persisted_payloads
):
    async def fail_if_called(**kwargs):
        raise AssertionError("duplicate job must not call Coze")

    monkeypatch.setattr("app.services.job_service.job_exists", lambda _job_id: True)
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fail_if_called,
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={"job_id": "already-saved", "job_name": "重复岗位"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 0}
    assert persisted_payloads == []


def test_bulk_evaluate_saves_fixed_score_without_calling_coze(
    monkeypatch, persisted_payloads
):
    async def fail_if_called(**kwargs):
        raise AssertionError("bulk evaluate must not call Coze")

    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fail_if_called,
    )

    response = client.post(
        "/api/v1/jobs/bulk-evaluate",
        json={
            "job_id": "bulk-job",
            "job_name": "Python 开发工程师",
            "job_tags": ["Python"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 71}
    assert persisted_payloads == [
        {
            "job_id": "bulk-job",
            "job_name": "Python 开发工程师",
            "job_tags": ["Python"],
            "coze_output": {
                "match_score": 71,
                "bulk_apply": True,
                "evaluation_source": "bulk_apply_default",
            },
        }
    ]
    assert persisted_payloads.application_statuses == ["沟通"]


@pytest.mark.parametrize(
    ("job_id", "job_name"),
    [
        ("already-saved", "普通岗位"),
        ("new-blacklisted", "亚马逊英语客服（双休）"),
    ],
)
def test_bulk_evaluate_skips_duplicates_and_blacklist(
    monkeypatch, persisted_payloads, job_id, job_name
):
    monkeypatch.setattr(
        "app.services.job_service.job_exists",
        lambda candidate: candidate == "already-saved",
    )

    response = client.post(
        "/api/v1/jobs/bulk-evaluate",
        json={"job_id": job_id, "job_name": job_name},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 0}
    assert persisted_payloads == []


def test_protected_ai_job_continues_to_coze(monkeypatch, tmp_path):
    calls = []

    async def fake_run_job_evaluation(**kwargs):
        calls.append(kwargs)
        return {"match_score": 88}

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path, match_threshold=70),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={
            "job_name": "AI应用开发工程师",
            "job_description": "使用 Python、Agent 和 FastAPI 开发 AI 应用",
            "job_tags": ["Python", "Agent", "FastAPI"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 88}
    assert len(calls) == 1
    assert calls[0]["job_name"] == "AI应用开发工程师"


def test_evaluate_returns_502_and_does_not_save_invalid_coze_output(
    monkeypatch, tmp_path, persisted_payloads
):
    async def fake_run_job_evaluation(**kwargs):
        raise CozeResponseError("Coze Workflow 输出缺少 match_score")

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={"job_name": "AI Agent 工程师"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Coze Workflow 输出缺少 match_score"}
    assert persisted_payloads == []


def test_evaluate_uses_fallback_score_and_saves_result_on_coze_timeout(
    monkeypatch, tmp_path, persisted_payloads
):
    async def fake_run_job_evaluation(**kwargs):
        raise CozeTimeoutError("Coze Workflow 请求超时")

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(
            data_dir=tmp_path,
            coze_timeout_fallback_score=50,
            match_threshold=70,
        ),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={"job_id": "timeout-job", "job_name": "Coze 超时岗位"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 50}
    assert len(persisted_payloads) == 1
    saved = persisted_payloads[0]
    assert saved["job_id"] == "timeout-job"
    assert saved["coze_output"] == {
        "match_score": 50,
        "fallback": True,
        "fallback_reason": "COZE_TIMEOUT",
    }
    assert persisted_payloads.application_statuses == ["未投递"]


def test_evaluate_schedules_introduction_only_for_high_score_with_context(
    monkeypatch, tmp_path
):
    scheduled = []

    async def fake_run_job_evaluation(**kwargs):
        return {
            "match_score": 82,
            "self_intro_context": [
                {
                    "target_requirements": ["Python"],
                    "relevant_experiences": [],
                    "matched_skills": ["Python"],
                    "highlight_points": [],
                }
            ],
        }

    scheduled_application_ids = []

    def fake_schedule(background_tasks, context, application_id=None):
        scheduled.append(context)
        scheduled_application_ids.append(application_id)
        return "task-123"

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path, match_threshold=70),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )
    monkeypatch.setattr(
        "app.services.introduction_service.schedule_introduction_generation",
        fake_schedule,
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={
            "job_name": "Python工程师",
            "company_name": "示例公司",
            "hr_name": "朱先生",
            "hr_title": "招聘经理",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 82}
    assert len(scheduled) == 1
    assert scheduled[0].company_name == "示例公司"
    assert scheduled[0].self_intro_context[0]["matched_skills"] == ["Python"]
    assert scheduled_application_ids == [42]


def test_evaluate_does_not_schedule_for_low_score_even_with_context(
    monkeypatch, tmp_path
):
    scheduled = []

    async def fake_run_job_evaluation(**kwargs):
        return {
            "match_score": 69,
            "self_intro_context": [{"target_requirements": ["Python"]}],
        }

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path, match_threshold=70),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )
    monkeypatch.setattr(
        "app.services.introduction_service.schedule_introduction_generation",
        lambda *args: scheduled.append(args),
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={"job_name": "低分岗位"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 69}
    assert scheduled == []


def test_evaluate_does_not_schedule_when_context_is_empty(monkeypatch, tmp_path):
    scheduled = []

    async def fake_run_job_evaluation(**kwargs):
        return {"match_score": 85, "self_intro_context": []}

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path, match_threshold=70),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )
    monkeypatch.setattr(
        "app.services.introduction_service.schedule_introduction_generation",
        lambda *args: scheduled.append(args),
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={"job_name": "高分但无上下文"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 85}
    assert scheduled == []


def test_invalid_introduction_context_does_not_fail_evaluate(monkeypatch, tmp_path):
    async def fake_run_job_evaluation(**kwargs):
        return {"match_score": 85, "self_intro_context": ["invalid-item"]}

    monkeypatch.setattr(
        "app.services.job_service.settings",
        SimpleNamespace(data_dir=tmp_path, match_threshold=70),
    )
    monkeypatch.setattr(
        "app.services.job_service.run_job_evaluation",
        fake_run_job_evaluation,
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={"job_name": "结构异常岗位"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 85}


def test_realtime_flow_persists_status_and_first_communication(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'realtime.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    async def fake_evaluation(**kwargs):
        return {
            "match_score": 85,
            "self_intro_context": [{"matched_skills": ["Python"]}],
        }

    async def fake_introduction(**kwargs):
        return "您好，我有 Python 项目经验。"

    async def fake_enqueue(message):
        return None

    def save_job(payload, **kwargs):
        return database_save_job_result(payload, session_factory=sessions, **kwargs)

    def save_communication(application_id, content):
        return database_save_first_communication(
            application_id,
            content,
            session_factory=sessions,
        )

    monkeypatch.setattr(
        "app.services.job_service.settings", SimpleNamespace(match_threshold=70)
    )
    monkeypatch.setattr(
        "app.services.introduction_service.settings",
        SimpleNamespace(match_threshold=70),
    )
    monkeypatch.setattr("app.services.job_service.run_job_evaluation", fake_evaluation)
    monkeypatch.setattr("app.services.job_service.save_job_result", save_job)
    monkeypatch.setattr(
        "app.services.introduction_service.run_introduction_workflow",
        fake_introduction,
    )
    monkeypatch.setattr(
        "app.services.introduction_service.save_first_communication",
        save_communication,
    )
    monkeypatch.setattr(
        "app.services.introduction_service.chat_assistant_manager.enqueue", fake_enqueue
    )

    response = client.post(
        "/api/v1/jobs/evaluate",
        json={"job_id": "realtime-1", "job_name": "Python实时开发工程师"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "match_score": 85}
    with sessions() as session:
        application = session.scalar(select(Application))
        communication = session.scalar(select(Communication))
        assert application.status == "沟通"
        assert communication.application_id == application.id
        assert communication.content == "您好，我有 Python 项目经验。"
