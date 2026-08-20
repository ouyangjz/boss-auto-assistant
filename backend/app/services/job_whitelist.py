import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from app.core.config import settings
from app.services.rule_config_cache import RuleConfigCache

logger = logging.getLogger("uvicorn.error")

_config_cache = RuleConfigCache(
    logger=logger,
    log_prefix="WHITELIST",
    empty_cache_effect="bulk evaluation denied",
)


def _normalize(value: str) -> str:
    """只去除首尾空格并忽略英文大小写。"""
    return value.strip().casefold()


def _load_config(config_path: Path) -> Optional[Dict[str, Any]]:
    return _config_cache.load(config_path)


def check_job_whitelist(
    job_data: Mapping[str, Any], config_path: Optional[Path] = None
) -> Dict[str, Any]:
    """检查海投白名单；配置异常时沿用最后有效配置，无缓存时拒绝。"""
    path = Path(config_path or settings.job_whitelist_config)
    config = _load_config(path)
    if not config or not config.get("enabled", True):
        return {"matched": False}

    raw_job_name = job_data.get("job_name", "")
    job_name = _normalize(raw_job_name) if isinstance(raw_job_name, str) else ""

    for rule in config.get("job_name_exact", []):
        normalized_rule = _normalize(rule)
        if normalized_rule and job_name == normalized_rule:
            return {
                "matched": True,
                "rule_type": "job_name_exact",
                "rule": rule,
            }

    for rule in config.get("job_name_contains", []):
        normalized_rule = _normalize(rule)
        if normalized_rule and normalized_rule in job_name:
            return {
                "matched": True,
                "rule_type": "job_name_contains",
                "rule": rule,
            }

    raw_tags = job_data.get("job_tags", [])
    tags = raw_tags if isinstance(raw_tags, list) else []
    normalized_tags = [
        _normalize(tag) for tag in tags if isinstance(tag, str) and tag.strip()
    ]
    for rule in config.get("job_tag_contains", []):
        normalized_rule = _normalize(rule)
        if normalized_rule and any(
            normalized_rule in tag for tag in normalized_tags
        ):
            return {
                "matched": True,
                "rule_type": "job_tag_contains",
                "rule": rule,
            }

    return {"matched": False}
