from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status

from app.schemas.management import (
    ManagementConfig,
    ManagementSettings,
    Rule,
    RuleCreate,
    RuleTestPayload,
    RuleTestResponse,
    RuleUpdate,
)
from app.services.rule_service import RuleNotFoundError, rule_service


router = APIRouter()
RuleListName = Literal["blacklist", "whitelist"]


def _update_rule(list_name: RuleListName, rule_id: str, payload: RuleUpdate) -> Rule:
    try:
        return rule_service.update_rule(list_name, rule_id, payload)
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail="规则不存在") from exc


def _delete_rule(list_name: RuleListName, rule_id: str) -> Response:
    try:
        rule_service.delete_rule(list_name, rule_id)
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail="规则不存在") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/config", response_model=ManagementConfig)
async def get_management_config() -> ManagementConfig:
    return rule_service.get_config()


@router.patch("/settings", response_model=ManagementSettings)
async def update_management_settings(
    payload: ManagementSettings,
) -> ManagementSettings:
    return rule_service.update_settings(payload)


@router.post("/blacklist", response_model=Rule, status_code=status.HTTP_201_CREATED)
async def create_blacklist_rule(payload: RuleCreate) -> Rule:
    return rule_service.create_rule("blacklist", payload)


@router.patch("/blacklist/{rule_id}", response_model=Rule)
async def update_blacklist_rule(rule_id: str, payload: RuleUpdate) -> Rule:
    return _update_rule("blacklist", rule_id, payload)


@router.delete("/blacklist/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blacklist_rule(rule_id: str) -> Response:
    return _delete_rule("blacklist", rule_id)


@router.post("/whitelist", response_model=Rule, status_code=status.HTTP_201_CREATED)
async def create_whitelist_rule(payload: RuleCreate) -> Rule:
    return rule_service.create_rule("whitelist", payload)


@router.patch("/whitelist/{rule_id}", response_model=Rule)
async def update_whitelist_rule(rule_id: str, payload: RuleUpdate) -> Rule:
    return _update_rule("whitelist", rule_id, payload)


@router.delete("/whitelist/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whitelist_rule(rule_id: str) -> Response:
    return _delete_rule("whitelist", rule_id)


@router.post("/test", response_model=RuleTestResponse)
async def test_rules(payload: RuleTestPayload) -> RuleTestResponse:
    return rule_service.test_rules(payload)
