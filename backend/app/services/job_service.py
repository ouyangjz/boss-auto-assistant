import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.config import settings
from app.database.services import job_exists, save_job_result
from app.schemas.job import JobEvaluateResponse, JobPayload
from app.services.coze_client import CozeTimeoutError, run_job_evaluation
from app.services.job_whitelist import check_job_whitelist
from app.services.rule_service import evaluate_local_rules, get_match_threshold


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class JobEvaluationResult:
    response: JobEvaluateResponse
    coze_output: Dict[str, Any]
    application_database_id: Optional[int]


class JobService:
    """按本地规则、Coze 结果和动态阈值评估并持久化岗位。"""

    @staticmethod
    def _raw_payload(payload: JobPayload) -> Dict[str, Any]:
        if hasattr(payload, "model_dump"):
            raw_payload = payload.model_dump(exclude_unset=True)  # Pydantic 2
        else:
            raw_payload = payload.dict(exclude_unset=True)  # Pydantic 1
        if not raw_payload.get("location"):
            raw_payload.pop("location", None)
        return raw_payload

    @staticmethod
    def _skipped_result(
        reason: str,
        decision_source: str,
        *,
        threshold: int,
        matched_rule: Optional[Dict[str, Any]] = None,
    ) -> JobEvaluationResult:
        coze_output = {
            "match_score": 0,
            "decision_source": decision_source,
            "reason": reason,
            "matched_rule": matched_rule,
        }
        return JobEvaluationResult(
            response=JobEvaluateResponse(
                success=True,
                match_score=0,
                should_contact=False,
                match_threshold=threshold,
                decision_source=decision_source,
                reason=reason,
                matched_rule=matched_rule,
            ),
            coze_output=coze_output,
            application_database_id=None,
        )

    def _check_should_skip(
        self,
        payload: JobPayload,
        raw_payload: Dict[str, Any],
    ) -> Optional[JobEvaluationResult]:
        threshold = get_match_threshold()
        if payload.job_id.strip() and job_exists(payload.job_id):
            logger.info(
                "[DUPLICATE SKIP] job_id=%s job=%s",
                payload.job_id,
                payload.job_name,
            )
            return self._skipped_result(
                "duplicate", "duplicate", threshold=threshold
            )

        local_result = evaluate_local_rules(raw_payload)
        if local_result["result"] == "blacklist":
            matched_rule = local_result["matched_rule"]
            logger.info(
                "[BLACKLIST SKIP] job=%s target=%s rule=%s",
                payload.job_name,
                matched_rule["target"],
                matched_rule["keyword"],
            )
            return self._skipped_result(
                "blacklist",
                "blacklist",
                threshold=threshold,
                matched_rule=matched_rule,
            )
        return None

    async def evaluate(self, payload: JobPayload) -> JobEvaluationResult:
        raw_payload = self._raw_payload(payload)
        logger.info("Received job: %s", payload.job_name)

        skipped = self._check_should_skip(payload, raw_payload)
        if skipped is not None:
            return skipped

        threshold = get_match_threshold()
        local_result = evaluate_local_rules(raw_payload)
        if local_result["result"] == "whitelist":
            matched_rule = local_result["matched_rule"]
            logger.info(
                "[WHITELIST PASS] job=%s target=%s rule=%s",
                payload.job_name,
                matched_rule["target"],
                matched_rule["keyword"],
            )
            # 白名单不是 AI 评分；使用当前阈值作为兼容插件的通过分。
            match_score = threshold
            coze_output = {
                "match_score": match_score,
                "decision_source": "whitelist",
                "matched_rule": matched_rule,
            }
            saved = save_job_result(
                {**raw_payload, "coze_output": coze_output},
                application_status="沟通",
            )
            return JobEvaluationResult(
                response=JobEvaluateResponse(
                    success=True,
                    match_score=match_score,
                    should_contact=True,
                    match_threshold=threshold,
                    decision_source="whitelist",
                    matched_rule=matched_rule,
                ),
                coze_output=coze_output,
                application_database_id=saved.application_database_id,
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
            coze_output = {
                "match_score": fallback_score,
                "fallback": True,
                "fallback_reason": "COZE_TIMEOUT",
            }
        match_score = int(coze_output["match_score"])
        should_contact = match_score >= threshold
        coze_output = {**coze_output, "decision_source": "coze"}
        saved = save_job_result(
            {**raw_payload, "coze_output": coze_output},
            application_status="沟通" if should_contact else "未投递",
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
                should_contact=should_contact,
                match_threshold=threshold,
                decision_source="coze",
            ),
            coze_output=coze_output,
            application_database_id=saved.application_database_id,
        )

    async def bulk_evaluate(self, payload: JobPayload) -> JobEvaluationResult:
        """Persist an eligible bulk-application job without invoking Coze."""
        raw_payload = self._raw_payload(payload)
        logger.info("Received bulk-application job: %s", payload.job_name)

        skipped = self._check_should_skip(payload, raw_payload)
        if skipped is not None:
            return skipped

        threshold = get_match_threshold()
        whitelist_result = check_job_whitelist(raw_payload)
        if not whitelist_result["matched"]:
            logger.info(
                "[WHITELIST SKIP] job_id=%s job=%s",
                payload.job_id,
                payload.job_name,
            )
            return self._skipped_result(
                "not_whitelisted", "bulk_filter", threshold=threshold
            )
        logger.info(
            "[WHITELIST MATCH] job=%s rule_type=%s rule=%s",
            payload.job_name,
            whitelist_result["rule_type"],
            whitelist_result["rule"],
        )

        match_score = 71
        coze_output = {
            "match_score": match_score,
            "bulk_apply": True,
            "evaluation_source": "bulk_apply_default",
            "decision_source": "whitelist",
        }
        saved = save_job_result(
            {**raw_payload, "coze_output": coze_output},
            application_status="沟通",
        )
        logger.info(
            "Saved bulk-application result: job_db_id=%s evaluation_db_id=%s",
            saved.job_database_id,
            saved.evaluation_database_id,
        )
        return JobEvaluationResult(
            response=JobEvaluateResponse(
                success=True,
                match_score=match_score,
                should_contact=True,
                match_threshold=threshold,
                decision_source="whitelist",
            ),
            coze_output=coze_output,
            application_database_id=saved.application_database_id,
        )
