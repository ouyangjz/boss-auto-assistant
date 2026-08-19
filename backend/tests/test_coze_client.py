import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.coze_client import (
    CozeConfigurationError,
    CozeResponseError,
    parse_workflow_output,
    run_job_evaluation,
)


def test_parse_workflow_output_decodes_data_and_normalizes_score():
    workflow_output = {
        "job_category": "后端开发",
        "match_score": "83",
        "required_skills": ["Python"],
    }
    result = parse_workflow_output(
        {"code": 0, "msg": "Success", "data": json.dumps(workflow_output)}
    )

    assert result == {
        "job_category": "后端开发",
        "match_score": 83,
        "required_skills": ["Python"],
    }


def test_parse_workflow_output_supports_nested_output_wrapper():
    result = parse_workflow_output(
        {
            "code": 0,
            "data": {
                "output": json.dumps(
                    {"match_score": 76, "summary": "可进一步沟通"}
                )
            },
        }
    )

    assert result == {"match_score": 76, "summary": "可进一步沟通"}


@pytest.mark.parametrize(
    "response",
    [
        {"code": 0, "data": json.dumps({"summary": "缺少分数"})},
        {"code": 0, "data": json.dumps({"match_score": "高"})},
        {"code": 0, "data": json.dumps({"match_score": 101})},
        {"code": 4000, "msg": "Workflow failed", "data": "{}"},
    ],
)
def test_parse_workflow_output_rejects_invalid_results(response):
    with pytest.raises(CozeResponseError):
        parse_workflow_output(response)


def test_run_job_evaluation_sends_only_required_job_parameters(monkeypatch):
    monkeypatch.setattr(
        "app.services.coze_client.settings",
        SimpleNamespace(
            coze_base_url="http://coze.local/",
            coze_workflow_id="workflow-123",
            coze_token="secret-token",
        ),
    )
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": json.dumps(
                    {"match_score": 83, "summary": "适合进一步沟通"}
                ),
            },
        )

    async def call_client():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await run_job_evaluation(
                job_name="AI智能体开发",
                job_description="第一行\n第二行",
                job_tags=["Python", "SQL"],
                client=client,
            )

    result = asyncio.run(call_client())

    assert captured == {
        "url": "http://coze.local/v1/workflow/run",
        "authorization": "Bearer secret-token",
        "body": {
            "workflow_id": "workflow-123",
            "parameters": {
                "job_name": "AI智能体开发",
                "job_description": "第一行\n第二行",
                "job_tags": ["Python", "SQL"],
            },
        },
    }
    assert result == {"match_score": 83, "summary": "适合进一步沟通"}


def test_run_job_evaluation_reports_missing_configuration(monkeypatch):
    monkeypatch.setattr(
        "app.services.coze_client.settings",
        SimpleNamespace(
            coze_base_url="",
            coze_workflow_id="workflow-123",
            coze_token="secret-token",
        ),
    )

    with pytest.raises(CozeConfigurationError, match="COZE_BASE_URL 未配置"):
        asyncio.run(
            run_job_evaluation(
                job_name="岗位",
                job_description="描述",
                job_tags=[],
            )
        )
