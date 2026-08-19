import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.coze_client import CozeResponseError
from app.services.introduction_service import (
    generate_and_dispatch_introduction,
    parse_introduction_output,
    run_introduction_workflow,
)
from app.schemas.introduction import IntroductionTaskContext


def test_parse_introduction_output_supports_nested_coze_result():
    result = parse_introduction_output(
        {
            "code": 0,
            "data": json.dumps(
                {"output": json.dumps({"greeting_message": "你好，很高兴沟通。"})}
            ),
        }
    )

    assert result == "你好，很高兴沟通。"


def test_parse_introduction_output_unwraps_json_inside_greeting_message():
    nested_greeting = json.dumps(
        {
            "greeting_message": (
                "我主要做过基于RAG的智能旅行规划系统，也完成过微服务开发部署。"
            )
        },
        ensure_ascii=False,
    )

    result = parse_introduction_output(
        {
            "code": 0,
            "data": json.dumps(
                {"greeting_message": nested_greeting},
                ensure_ascii=False,
            ),
        }
    )

    assert result == "我主要做过基于RAG的智能旅行规划系统，也完成过微服务开发部署。"


def test_parse_introduction_output_rejects_missing_greeting():
    with pytest.raises(CozeResponseError, match="缺少 greeting_message"):
        parse_introduction_output({"code": 0, "data": {"summary": "没有招呼语"}})


def test_run_introduction_workflow_preserves_context_structure(monkeypatch):
    monkeypatch.setattr(
        "app.services.introduction_service.settings",
        SimpleNamespace(
            coze_base_url="http://coze.local/",
            coze_introduction_workflow_id="intro-workflow",
            coze_token="secret-token",
            coze_introduction_timeout_seconds=30,
        ),
    )
    captured = {}
    context = [{"target_requirements": ["Python"], "matched_skills": ["FastAPI"]}]

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"code": 0, "data": json.dumps({"greeting_message": "你好"})},
        )

    async def call_workflow():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await run_introduction_workflow(
                job_name="Python工程师",
                self_intro_context=context,
                client=client,
            )

    result = asyncio.run(call_workflow())

    assert result == "你好"
    assert captured["body"] == {
        "workflow_id": "intro-workflow",
        "parameters": {
            "job_name": "Python工程师",
            "self_intro_context": context,
        },
    }


def test_generated_introduction_is_saved_before_dispatch(monkeypatch):
    saved = []
    dispatched = []

    async def fake_workflow(**kwargs):
        return "您好，我有 Python 和 FastAPI 项目经验。"

    def fake_save(application_id, content):
        saved.append((application_id, content))
        return SimpleNamespace(communication_database_id=9, created=True)

    async def fake_enqueue(message):
        dispatched.append(message)

    monkeypatch.setattr(
        "app.services.introduction_service.run_introduction_workflow",
        fake_workflow,
    )
    monkeypatch.setattr(
        "app.services.introduction_service.save_first_communication",
        fake_save,
    )
    monkeypatch.setattr(
        "app.services.introduction_service.plugin_two_manager.enqueue",
        fake_enqueue,
    )
    context = IntroductionTaskContext(
        job_name="Python工程师",
        match_score=88,
        self_intro_context=[{"matched_skills": ["Python"]}],
    )

    asyncio.run(generate_and_dispatch_introduction("task-1", context, 7))

    assert saved == [(7, "您好，我有 Python 和 FastAPI 项目经验。")]
    assert dispatched[0]["greeting_message"] == "您好，我有 Python 和 FastAPI 项目经验。"
