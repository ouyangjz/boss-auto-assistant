import json
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")


class CozeWorkflowError(Exception):
    """Coze Workflow 调用失败。"""


class CozeConfigurationError(CozeWorkflowError):
    """Coze 配置缺失。"""


class CozeRequestError(CozeWorkflowError):
    """无法成功请求 Coze API。"""


class CozeTimeoutError(CozeRequestError):
    """Coze API 请求超时。"""


class CozeResponseError(CozeWorkflowError):
    """Coze API 响应或 Workflow 输出无效。"""


def _required_setting(attribute: str, environment_name: str) -> str:
    value = str(getattr(settings, attribute, "")).strip()
    if not value:
        raise CozeConfigurationError(f"{environment_name} 未配置")
    return value


def _decode_json(value: Any) -> Any:
    """解码 Coze 常见的 JSON 字符串结果，不对普通文本做猜测解析。"""
    decoded = value
    for _ in range(3):
        if not isinstance(decoded, str):
            break
        try:
            decoded = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise CozeResponseError("Coze Workflow 输出不是合法 JSON") from exc
    return decoded


def parse_workflow_output(api_response: Any) -> Dict[str, Any]:
    """从 Coze API 外层响应中提取最终 Workflow 业务输出。"""
    response_data = _decode_json(api_response)
    if not isinstance(response_data, dict):
        raise CozeResponseError("Coze API 响应必须是 JSON 对象")

    if "code" in response_data and str(response_data["code"]) != "0":
        message = response_data.get("msg") or response_data.get("message") or "未知错误"
        raise CozeResponseError(
            f"Coze API 返回业务错误 code={response_data['code']}: {message}"
        )

    output = response_data.get("data", response_data)
    output = _decode_json(output)

    if isinstance(output, dict) and "match_score" not in output:
        # 兼容部分 Coze Studio 版本在 data 内再使用 output/result 包装业务结果。
        for key in ("output", "result"):
            if key in output:
                candidate = _decode_json(output[key])
                if isinstance(candidate, dict) and "match_score" in candidate:
                    output = candidate
                    break

    if not isinstance(output, dict):
        raise CozeResponseError("Coze Workflow 最终输出必须是 JSON 对象")
    if "match_score" not in output:
        raise CozeResponseError("Coze Workflow 输出缺少 match_score")

    raw_score = output["match_score"]
    if isinstance(raw_score, bool):
        raise CozeResponseError("Coze Workflow 的 match_score 不是有效整数")
    if isinstance(raw_score, int):
        score = raw_score
    elif isinstance(raw_score, str):
        try:
            score = int(raw_score.strip())
        except ValueError as exc:
            raise CozeResponseError(
                "Coze Workflow 的 match_score 不是有效整数"
            ) from exc
    else:
        raise CozeResponseError("Coze Workflow 的 match_score 不是有效整数")

    if not 0 <= score <= 100:
        raise CozeResponseError("Coze Workflow 的 match_score 必须在 0 到 100 之间")

    # 数字字符串只做安全的整数归一化，其他 Workflow 输出保持原样。
    output["match_score"] = score
    return output


async def run_job_evaluation(
    job_name: str,
    job_description: str,
    job_tags: list[str],
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """调用 Coze Workflow 并返回完整、已校验的业务输出。"""
    base_url = _required_setting("coze_base_url", "COZE_BASE_URL")
    workflow_id = _required_setting("coze_workflow_id", "COZE_WORKFLOW_ID")
    token = _required_setting("coze_token", "COZE_TOKEN")
    url = f"{base_url.rstrip('/')}/v1/workflow/run"
    request_body = {
        "workflow_id": workflow_id,
        "parameters": {
            "job_name": job_name,
            "job_description": job_description,
            "job_tags": job_tags,
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    logger.info("[COZE EVALUATE] calling workflow: %s", workflow_id)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.coze_timeout_seconds)
    try:
        try:
            response = await http_client.post(url, headers=headers, json=request_body)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("Coze workflow request timed out: %s", exc)
            raise CozeTimeoutError("Coze Workflow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Coze workflow HTTP error: status=%s response=%s",
                exc.response.status_code,
                exc.response.text,
            )
            raise CozeRequestError(
                f"Coze Workflow 返回 HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Coze workflow request failed: %s", exc)
            raise CozeRequestError("无法连接 Coze Workflow 服务") from exc

        try:
            api_response = response.json()
            output = parse_workflow_output(api_response)
        except (json.JSONDecodeError, CozeResponseError) as exc:
            logger.error("Invalid Coze workflow response: %s", response.text)
            if isinstance(exc, CozeResponseError):
                raise
            raise CozeResponseError("Coze API 响应不是合法 JSON") from exc

        logger.info("[COZE EVALUATE] workflow completed")
        return output
    finally:
        if owns_client:
            await http_client.aclose()
