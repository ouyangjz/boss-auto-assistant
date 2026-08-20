import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks

from app.core.config import settings
from app.database.services import save_first_communication
from app.schemas.introduction import IntroductionReadyMessage, IntroductionTaskContext
from app.schemas.job import JobPayload
from app.services.coze_client import (
    CozeConfigurationError,
    CozeRequestError,
    CozeResponseError,
    CozeTimeoutError,
)
from app.services.websocket_manager import chat_assistant_manager
from app.services.rule_service import get_match_threshold

logger = logging.getLogger("uvicorn.error")


def _model_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # Pydantic 2
    return model.dict()  # Pydantic 1


def _maybe_decode_json(value: Any) -> Any:
    decoded = value
    for _ in range(3):
        if not isinstance(decoded, str):
            break
        stripped = decoded.strip()
        if not stripped:
            return ""
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
    return decoded


def _find_greeting(value: Any) -> str:
    decoded = _maybe_decode_json(value)
    if isinstance(decoded, str):
        return decoded.strip()
    if not isinstance(decoded, dict):
        return ""

    for key in ("greeting_message", "greeting", "message", "reply"):
        if key not in decoded:
            continue
        candidate = _maybe_decode_json(decoded[key])
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        nested_greeting = _find_greeting(candidate)
        if nested_greeting:
            return nested_greeting

    for key in ("output", "result", "data"):
        if key in decoded:
            candidate = _find_greeting(decoded[key])
            if candidate:
                return candidate
    return ""


def parse_introduction_output(api_response: Any) -> str:
    response_data = _maybe_decode_json(api_response)
    if not isinstance(response_data, dict):
        raise CozeResponseError("自我介绍 Workflow 响应必须是 JSON 对象")

    if "code" in response_data and str(response_data["code"]) != "0":
        message = response_data.get("msg") or response_data.get("message") or "未知错误"
        raise CozeResponseError(
            f"自我介绍 Workflow 返回业务错误 code={response_data['code']}: {message}"
        )

    greeting = _find_greeting(response_data.get("data", response_data))
    if not greeting:
        raise CozeResponseError("自我介绍 Workflow 输出缺少 greeting_message")
    return greeting


async def run_introduction_workflow(
    job_name: str,
    self_intro_context: list[dict[str, Any]],
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    base_url = str(settings.coze_base_url).strip()
    workflow_id = str(settings.coze_introduction_workflow_id).strip()
    token = str(settings.coze_token).strip()
    if not base_url:
        raise CozeConfigurationError("COZE_BASE_URL 未配置")
    if not workflow_id:
        raise CozeConfigurationError("COZE_INTRODUCTION_WORKFLOW_ID 未配置")
    if not token:
        raise CozeConfigurationError("COZE_TOKEN 未配置")

    url = f"{base_url.rstrip('/')}/v1/workflow/run"
    request_body = {
        "workflow_id": workflow_id,
        "parameters": {
            "job_name": job_name,
            "self_intro_context": self_intro_context,
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        timeout=settings.coze_introduction_timeout_seconds
    )
    try:
        try:
            response = await http_client.post(url, headers=headers, json=request_body)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise CozeTimeoutError("自我介绍 Workflow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            raise CozeRequestError(
                f"自我介绍 Workflow 返回 HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise CozeRequestError("无法连接自我介绍 Workflow 服务") from exc

        try:
            return parse_introduction_output(response.json())
        except json.JSONDecodeError as exc:
            raise CozeResponseError("自我介绍 API 响应不是合法 JSON") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def generate_and_dispatch_introduction(
    task_id: str,
    context: IntroductionTaskContext,
    application_id: Optional[int] = None,
) -> None:
    logger.info("[Introduction] generating task=%s", task_id)
    try:
        greeting_message = await run_introduction_workflow(
            job_name=context.job_name,
            self_intro_context=context.self_intro_context,
        )
        if application_id is not None:
            try:
                saved = save_first_communication(application_id, greeting_message)
                logger.info(
                    "[Introduction] communication saved application=%s "
                    "communication=%s created=%s",
                    application_id,
                    saved.communication_database_id,
                    saved.created,
                )
            except Exception:
                # 沟通语落库失败不能阻断原有插件推送流程。
                logger.exception(
                    "[Introduction] communication persistence failed application=%s",
                    application_id,
                )
        message = IntroductionReadyMessage(
            **_model_dict(context),
            task_id=task_id,
            greeting_message=greeting_message,
            created_at=datetime.now().astimezone().replace(microsecond=0).isoformat(),
        )
        logger.info("[Introduction] generated task=%s", task_id)
        await chat_assistant_manager.enqueue(_model_dict(message))
    except Exception:
        # 这是 evaluate 之外的附加链路；任何异常都只记录，不能反向影响岗位评估。
        logger.exception("[Introduction] generation failed task=%s", task_id)


def schedule_introduction_generation(
    background_tasks: BackgroundTasks,
    context: IntroductionTaskContext,
    application_id: Optional[int] = None,
) -> str:
    task_id = str(uuid4())
    background_tasks.add_task(
        generate_and_dispatch_introduction,
        task_id,
        context,
        application_id,
    )
    logger.info("[Introduction] background task created: %s", task_id)
    return task_id


def schedule_introduction_for_evaluation(
    background_tasks: BackgroundTasks,
    payload: JobPayload,
    coze_output: Dict[str, Any],
    application_id: Optional[int] = None,
) -> Optional[str]:
    """按岗位评估结果决定是否异步进入独立自我介绍链路。"""
    match_score = int(coze_output["match_score"])
    threshold = get_match_threshold()
    if match_score < threshold:
        logger.info(
            "[Evaluate] score=%s < threshold=%s, skip introduction generation",
            match_score,
            threshold,
        )
        return None

    logger.info("[Evaluate] score=%s >= threshold=%s", match_score, threshold)
    self_intro_context = coze_output.get("self_intro_context") or []
    if not self_intro_context:
        logger.info(
            "[Introduction] self_intro_context is empty, skip introduction generation"
        )
        return None
    if not isinstance(self_intro_context, list):
        logger.warning(
            "[Introduction] self_intro_context must be a list, "
            "skip introduction generation"
        )
        return None

    logger.info("[Introduction] self_intro_context available")
    try:
        context = IntroductionTaskContext(
            company_name=payload.company_name,
            hr_name=payload.hr_name,
            hr_title=payload.hr_title,
            job_name=payload.job_name,
            match_score=match_score,
            self_intro_context=self_intro_context,
        )
        return schedule_introduction_generation(
            background_tasks,
            context,
            application_id=application_id,
        )
    except Exception:
        # 附加链路异常不能改变岗位评估的成功响应。
        logger.exception("[Introduction] failed to create background task, skip")
        return None
