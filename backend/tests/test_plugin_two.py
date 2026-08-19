from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_plugin_two_test_endpoint_pushes_message_and_accepts_ack():
    with client.websocket_connect("/ws/plugin-two") as websocket:
        response = client.post(
            "/api/v1/plugin-two/test",
            json={
                "company_name": "治粟科技",
                "hr_name": "朱先生",
                "hr_title": "招聘经理",
                "job_name": "python开发工程师",
                "greeting_message": "你好，这是测试消息。",
            },
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]

        message = websocket.receive_json()
        assert message == {
            "company_name": "治粟科技",
            "hr_name": "朱先生",
            "hr_title": "招聘经理",
            "job_name": "python开发工程师",
            "match_score": 100,
            "self_intro_context": [],
            "type": "introduction_ready",
            "task_id": task_id,
            "greeting_message": "你好，这是测试消息。",
            "created_at": message["created_at"],
        }

        websocket.send_json(
            {"type": "ack", "task_id": task_id, "status": "filled"}
        )
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}
