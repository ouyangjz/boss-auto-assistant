import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4

from app.core.config import settings
from app.schemas.management import (
    ManagementConfig,
    ManagementSettings,
    Rule,
    RuleCreate,
    RuleListName,
    RuleTestPayload,
    RuleTestResponse,
    RuleUpdate,
)
from app.services.rule_config_cache import RuleConfigCache


logger = logging.getLogger("uvicorn.error")


def _model_dump(model: Any, *, exclude_unset: bool = False) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _legacy_rule_id(prefix: str, target: str, match_type: str, keyword: str) -> str:
    digest = hashlib.sha1(
        f"{target}\0{match_type}\0{keyword}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _legacy_rules(config: Mapping[str, Any], prefix: str) -> List[Rule]:
    rules: List[Rule] = []
    mappings = (
        ("job_name_exact", "job_name", "exact"),
        ("job_name_contains", "job_name", "contains"),
        ("job_tag_contains", "job_tags", "contains"),
    )
    globally_enabled = config.get("enabled", True) is True
    for legacy_key, target, match_type in mappings:
        for keyword in config.get(legacy_key, []):
            rules.append(
                Rule(
                    id=_legacy_rule_id(prefix, target, match_type, keyword),
                    keyword=keyword,
                    target=target,
                    match_type=match_type,
                    enabled=globally_enabled,
                )
            )
    return rules


def rules_from_config(config: Optional[Mapping[str, Any]], prefix: str) -> List[Rule]:
    if not config:
        return []
    if "rules" not in config:
        return _legacy_rules(config, prefix)
    globally_enabled = config.get("enabled", True) is True
    return [
        Rule(**{**rule, "enabled": bool(rule.get("enabled")) and globally_enabled})
        for rule in config.get("rules", [])
    ]


def match_rule(job_data: Mapping[str, Any], rules: Iterable[Rule]) -> Optional[Rule]:
    for rule in rules:
        if not rule.enabled:
            continue
        raw_value = job_data.get(rule.target, "")
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        keyword = _normalize(rule.keyword)
        for value in values:
            if not isinstance(value, str):
                continue
            normalized_value = _normalize(value)
            if rule.match_type == "exact" and normalized_value == keyword:
                return rule
            if rule.match_type == "contains" and keyword in normalized_value:
                return rule
    return None


class RuleNotFoundError(LookupError):
    pass


class RuleService:
    """统一读取、匹配并安全写入岗位规则和动态运行设置。"""

    def __init__(
        self,
        *,
        blacklist_path: Optional[Path] = None,
        whitelist_path: Optional[Path] = None,
        settings_path: Optional[Path] = None,
        default_threshold: Optional[int] = None,
    ) -> None:
        self.blacklist_path = Path(blacklist_path or settings.job_blacklist_config)
        self.whitelist_path = Path(whitelist_path or settings.job_whitelist_config)
        self.settings_path = Path(settings_path or settings.job_settings_config)
        self.default_threshold = int(
            settings.match_threshold if default_threshold is None else default_threshold
        )
        self._blacklist_cache = RuleConfigCache(
            logger=logger,
            log_prefix="BLACKLIST",
            empty_cache_effect="blacklist disabled",
        )
        self._whitelist_cache = RuleConfigCache(
            logger=logger,
            log_prefix="WHITELIST",
            empty_cache_effect="whitelist disabled",
        )
        self._settings_state: Optional[tuple[Any, ...]] = None
        self._settings_cache: Optional[ManagementSettings] = None
        self._lock = RLock()

    def _path_for(self, list_name: RuleListName) -> Path:
        return self.blacklist_path if list_name == "blacklist" else self.whitelist_path

    def _cache_for(self, list_name: RuleListName) -> RuleConfigCache:
        return (
            self._blacklist_cache
            if list_name == "blacklist"
            else self._whitelist_cache
        )

    def get_rules(self, list_name: RuleListName) -> List[Rule]:
        config = self._cache_for(list_name).load(self._path_for(list_name))
        return rules_from_config(config, list_name)

    def _settings_file_state(self) -> tuple[Any, ...]:
        try:
            stat = self.settings_path.stat()
        except FileNotFoundError:
            return ("missing",)
        except OSError as exc:
            return ("error", type(exc).__name__, exc.errno, str(exc))
        return ("file", stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)

    def get_settings(self) -> ManagementSettings:
        with self._lock:
            state = self._settings_file_state()
            if state == self._settings_state and self._settings_cache is not None:
                return self._settings_cache

            if state[0] == "file":
                try:
                    payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
                    loaded = ManagementSettings(**payload)
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                    logger.warning(
                        "[RULE SETTINGS] invalid config; keeping last valid settings: %s (%s)",
                        self.settings_path,
                        exc,
                    )
                else:
                    self._settings_state = state
                    self._settings_cache = loaded
                    return loaded
            elif state[0] == "error":
                logger.warning("[RULE SETTINGS] cannot inspect config: %s", self.settings_path)

            if self._settings_cache is None:
                self._settings_cache = ManagementSettings(
                    match_threshold=self.default_threshold
                )
            self._settings_state = state
            return self._settings_cache

    @staticmethod
    def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            # 再解析一次临时文件，确保正式文件只会被合法 JSON 替换。
            json.loads(temporary_path.read_text(encoding="utf-8"))
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def update_settings(self, update: ManagementSettings) -> ManagementSettings:
        with self._lock:
            self._atomic_write(self.settings_path, _model_dump(update))
            self._settings_state = None
            self._settings_cache = update
            return update

    def _save_rules(self, list_name: RuleListName, rules: List[Rule]) -> None:
        payload = {
            "version": 1,
            "enabled": True,
            "rules": [_model_dump(rule) for rule in rules],
        }
        self._atomic_write(self._path_for(list_name), payload)
        self._cache_for(list_name).clear(self._path_for(list_name))

    def create_rule(self, list_name: RuleListName, create: RuleCreate) -> Rule:
        with self._lock:
            rules = self.get_rules(list_name)
            rule = Rule(id=f"rule_{uuid4().hex}", **_model_dump(create))
            rules.append(rule)
            self._save_rules(list_name, rules)
            return rule

    def update_rule(
        self, list_name: RuleListName, rule_id: str, update: RuleUpdate
    ) -> Rule:
        with self._lock:
            rules = self.get_rules(list_name)
            for index, current in enumerate(rules):
                if current.id != rule_id:
                    continue
                changes = {
                    key: value
                    for key, value in _model_dump(update, exclude_unset=True).items()
                    if value is not None
                }
                updated = Rule(**{**_model_dump(current), **changes})
                rules[index] = updated
                self._save_rules(list_name, rules)
                return updated
            raise RuleNotFoundError(rule_id)

    def delete_rule(self, list_name: RuleListName, rule_id: str) -> None:
        with self._lock:
            rules = self.get_rules(list_name)
            remaining = [rule for rule in rules if rule.id != rule_id]
            if len(remaining) == len(rules):
                raise RuleNotFoundError(rule_id)
            self._save_rules(list_name, remaining)

    def get_config(self) -> ManagementConfig:
        return ManagementConfig(
            settings=self.get_settings(),
            blacklist=self.get_rules("blacklist"),
            whitelist=self.get_rules("whitelist"),
        )

    def test_rules(self, payload: Any) -> RuleTestResponse:
        job_data = _model_dump(payload) if isinstance(payload, RuleTestPayload) else dict(payload)
        blacklist_rule = match_rule(job_data, self.get_rules("blacklist"))
        if blacklist_rule is not None:
            return RuleTestResponse(result="blacklist", matched_rule=blacklist_rule)
        whitelist_rule = match_rule(job_data, self.get_rules("whitelist"))
        if whitelist_rule is not None:
            return RuleTestResponse(result="whitelist", matched_rule=whitelist_rule)
        return RuleTestResponse(result="unmatched")


rule_service = RuleService()


def get_match_threshold() -> int:
    return rule_service.get_settings().match_threshold


def evaluate_local_rules(job_data: Mapping[str, Any]) -> Dict[str, Any]:
    blacklist_rule = match_rule(job_data, rule_service.get_rules("blacklist"))
    if blacklist_rule is not None:
        return {"result": "blacklist", "matched_rule": _model_dump(blacklist_rule)}
    whitelist_rule = match_rule(job_data, rule_service.get_rules("whitelist"))
    if whitelist_rule is not None:
        return {"result": "whitelist", "matched_rule": _model_dump(whitelist_rule)}
    return {"result": "unmatched", "matched_rule": None}
