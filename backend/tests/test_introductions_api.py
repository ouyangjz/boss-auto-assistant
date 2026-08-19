from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_generate_introduction_endpoint_schedules_background_task(monkeypatch):
    scheduled = []

    def fake_schedule(background_tasks, context):
        scheduled.append(context)
        return "intro-task-123"

    monkeypatch.setattr(
        "app.api.introductions.settings",
        SimpleNamespace(match_threshold=70),
    )
    monkeypatch.setattr(
        "app.api.introductions.schedule_introduction_generation",
        fake_schedule,
    )

    response = client.post(
        "/api/v1/introductions/generate",
        json={
            "company_name": "示例公司",
            "hr_name": "朱先生",
            "hr_title": "招聘经理",
            "job_name": "Python工程师",
            "match_score": 82,
            "self_intro_context": [
                {
                    "target_requirements": ["Python"],
                    "matched_skills": ["FastAPI"],
                }
            ],
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "success": True,
        "task_id": "intro-task-123",
        "status": "accepted",
    }
    assert len(scheduled) == 1
    assert scheduled[0].company_name == "示例公司"
    assert scheduled[0].self_intro_context[0]["matched_skills"] == ["FastAPI"]


def test_generate_introduction_endpoint_rejects_low_score(monkeypatch):
    monkeypatch.setattr(
        "app.api.introductions.settings",
        SimpleNamespace(match_threshold=70),
    )

    response = client.post(
        "/api/v1/introductions/generate",
        json={
            "job_name": "低分岗位",
            "match_score": 69,
            "self_intro_context": [{"target_requirements": ["Python"]}],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "match_score 必须大于等于阈值 70"}


def test_generate_introduction_endpoint_rejects_empty_context(monkeypatch):
    monkeypatch.setattr(
        "app.api.introductions.settings",
        SimpleNamespace(match_threshold=70),
    )

    response = client.post(
        "/api/v1/introductions/generate",
        json={"job_name": "高分岗位", "match_score": 85, "self_intro_context": []},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "self_intro_context 不能为空"}
