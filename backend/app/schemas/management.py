from typing import List, Literal, Optional

from pydantic import BaseModel, Field, constr


RuleTarget = Literal["job_name", "company_name", "job_description", "job_tags"]
# exact 仅用于兼容项目现有的精确岗位名规则；管理页新增规则仍固定为 contains。
RuleMatchType = Literal["contains", "exact"]
RuleListName = Literal["blacklist", "whitelist"]
RuleKeyword = constr(strip_whitespace=True, min_length=1, max_length=120)


class RuleBase(BaseModel):
    keyword: RuleKeyword
    target: RuleTarget
    match_type: RuleMatchType = "contains"
    enabled: bool = True

class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    keyword: Optional[RuleKeyword] = None
    target: Optional[RuleTarget] = None
    match_type: Optional[RuleMatchType] = None
    enabled: Optional[bool] = None

class Rule(RuleBase):
    id: str = Field(min_length=1, max_length=100)


class ManagementSettings(BaseModel):
    match_threshold: int = Field(ge=0, le=100)


class ManagementConfig(BaseModel):
    version: int = 1
    settings: ManagementSettings
    blacklist: List[Rule] = Field(default_factory=list)
    whitelist: List[Rule] = Field(default_factory=list)


class RuleTestPayload(BaseModel):
    job_name: str = ""
    company_name: str = ""
    job_description: str = ""


class RuleMatch(BaseModel):
    list_name: RuleListName
    rule: Rule


class RuleTestResponse(BaseModel):
    result: Literal["blacklist", "whitelist", "unmatched"]
    matched_rule: Optional[Rule] = None
