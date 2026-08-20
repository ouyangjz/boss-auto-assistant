import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Tuple


RULE_TYPES = (
    "job_name_exact",
    "job_name_contains",
    "job_tag_contains",
)
RULE_TARGETS = ("job_name", "company_name", "job_description", "job_tags")

FileState = Tuple[Any, ...]


@dataclass(frozen=True)
class _CacheEntry:
    observed_state: FileState
    config: Optional[Dict[str, Any]]


class RuleConfigCache:
    """按文件状态缓存规则配置，并在重载失败时保留最后一份有效配置。"""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        log_prefix: str,
        empty_cache_effect: str,
    ) -> None:
        self._logger = logger
        self._log_prefix = log_prefix
        self._empty_cache_effect = empty_cache_effect
        self._entries: Dict[Path, _CacheEntry] = {}
        self._lock = Lock()

    @staticmethod
    def _cache_key(config_path: Path) -> Path:
        return config_path.expanduser().resolve(strict=False)

    @staticmethod
    def _file_state(config_path: Path) -> Tuple[FileState, Optional[OSError]]:
        try:
            stat = config_path.stat()
        except FileNotFoundError as exc:
            return ("missing",), exc
        except OSError as exc:
            return ("stat_error", type(exc).__name__, exc.errno, str(exc)), exc
        return (
            "file",
            stat.st_mtime_ns,
            stat.st_ctime_ns,
            stat.st_size,
        ), None

    @staticmethod
    def _parse_config(
        config_path: Path,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return None, f"invalid config: {exc}"

        if not isinstance(config, dict) or not isinstance(config.get("enabled", True), bool):
            return None, "config must be an object with a boolean enabled field"

        rules = config.get("rules")
        if rules is not None:
            if not isinstance(rules, list):
                return None, "rules must be an array"
            seen_ids = set()
            for rule in rules:
                if not isinstance(rule, dict):
                    return None, "each rule must be an object"
                rule_id = rule.get("id")
                keyword = rule.get("keyword")
                if not isinstance(rule_id, str) or not rule_id.strip():
                    return None, "rule id must be a non-empty string"
                if rule_id in seen_ids:
                    return None, "rule ids must be unique"
                seen_ids.add(rule_id)
                if not isinstance(keyword, str) or not keyword.strip():
                    return None, "rule keyword must be a non-empty string"
                if rule.get("target") not in RULE_TARGETS:
                    return None, "rule target is invalid"
                if rule.get("match_type") not in ("contains", "exact"):
                    return None, "rule match_type is invalid"
                if not isinstance(rule.get("enabled"), bool):
                    return None, "rule enabled must be a boolean"

        for rule_type in RULE_TYPES:
            rules = config.get(rule_type, [])
            if not isinstance(rules, list) or not all(
                isinstance(rule, str) for rule in rules
            ):
                return None, f"{rule_type} must be a string array"
        return config, None

    def _warn_reload_failure(
        self,
        config_path: Path,
        reason: str,
        cached_config: Optional[Dict[str, Any]],
    ) -> None:
        if cached_config is not None:
            self._logger.warning(
                "[%s] %s; keeping last valid config: %s",
                self._log_prefix,
                reason,
                config_path,
            )
            return
        self._logger.warning(
            "[%s] %s, %s: %s",
            self._log_prefix,
            reason,
            self._empty_cache_effect,
            config_path,
        )

    def load(self, config_path: Path) -> Optional[Dict[str, Any]]:
        path = self._cache_key(config_path)
        with self._lock:
            state, stat_error = self._file_state(path)
            cached = self._entries.get(path)
            if cached is not None and cached.observed_state == state:
                return cached.config

            previous_config = cached.config if cached is not None else None
            if state[0] == "missing":
                self._warn_reload_failure(path, "config not found", previous_config)
                self._entries[path] = _CacheEntry(state, previous_config)
                return previous_config
            if state[0] == "stat_error":
                self._warn_reload_failure(
                    path,
                    f"cannot inspect config ({stat_error})",
                    previous_config,
                )
                self._entries[path] = _CacheEntry(state, previous_config)
                return previous_config

            config, error = self._parse_config(path)
            if config is None:
                self._warn_reload_failure(path, error or "invalid config", previous_config)
                self._entries[path] = _CacheEntry(state, previous_config)
                return previous_config

            self._entries[path] = _CacheEntry(state, config)
            return config

    def clear(self, config_path: Optional[Path] = None) -> None:
        """清除缓存；主要用于测试或显式强制重载。"""
        with self._lock:
            if config_path is None:
                self._entries.clear()
            else:
                self._entries.pop(self._cache_key(config_path), None)
