import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.config import settings
from app.database.services import save_job_result
from app.schemas.job import JobEvaluateResponse, JobPayload
from app.services.coze_client import CozeTimeoutError, run_job_evaluation
from app.services.job_blacklist import check_job_blacklist

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class JobEvaluationResult:
    response: JobEvaluateResponse
    coze_output: Dict[str, Any]
    application_database_id: Optional[int]


class JobService:
    """调用 Coze 评估岗位并持久化完整结果。"""

    async def evaluate(self, payload: JobPayload) -> JobEvaluationResult:
        if hasattr(payload, "model_dump"):
            # 只保存插件实际发送的字段，避免把 Schema 默认空值补进原始 JSON。
            raw_payload = payload.model_dump(exclude_unset=True)  # Pydantic 2
        else:
            raw_payload = payload.dict(exclude_unset=True)  # Pydantic 1
        if not raw_payload.get("location"):
            raw_payload.pop("location", None)
        logger.info("Received job: %s", payload.job_name)

        blacklist_result = check_job_blacklist(raw_payload)
        if blacklist_result["matched"]:
            logger.info(
                "[BLACKLIST SKIP] job=%s rule_type=%s rule=%s",
                payload.job_name,
                blacklist_result["rule_type"],
                blacklist_result["rule"],
            )
            return JobEvaluationResult(
                response=JobEvaluateResponse(success=True, match_score=0),
                coze_output={
                    "match_score": 0,
                    "blacklisted": True,
                    "blacklist_rule": blacklist_result["rule"],
                },
                application_database_id=None,
            )

        try:
            coze_output = await run_job_evaluation(
                job_name=payload.job_name,
                job_description=payload.job_description,
                job_tags=payload.job_tags,
            )
        except CozeTimeoutError:
            fallback_score = settings.coze_timeout_fallback_score
            logger.error(
                "Coze workflow timed out for job %s; using fallback match_score=%s",
                payload.job_name,
                fallback_score,
            )
            # 保留降级原因，避免默认分数被误认为 Coze 的真实评估结果。
            coze_output = {
                "match_score": fallback_score,
                "fallback": True,
                "fallback_reason": "COZE_TIMEOUT",
            }
        match_score = coze_output["match_score"]
        result_payload = {**raw_payload, "coze_output": coze_output}
        application_status = (
            "沟通" if int(match_score) >= settings.match_threshold else "未投递"
        )
        saved = save_job_result(
            result_payload,
            application_status=application_status,
        )

        logger.info("Match score: %s", match_score)
        logger.info(
            "Saved evaluation result: job_db_id=%s evaluation_db_id=%s",
            saved.job_database_id,
            saved.evaluation_database_id,
        )

        return JobEvaluationResult(
            response=JobEvaluateResponse(
                success=True,
                match_score=match_score,
            ),
            coze_output=coze_output,
            application_database_id=saved.application_database_id,
        )
