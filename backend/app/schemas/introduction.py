from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class IntroductionTaskContext(BaseModel):
    company_name: str = ""
    hr_name: str = ""
    hr_title: str = ""
    job_name: str = ""
    match_score: int = Field(ge=0, le=100)
    self_intro_context: List[Dict[str, Any]] = Field(default_factory=list)


class IntroductionReadyMessage(IntroductionTaskContext):
    type: Literal["introduction_ready"] = "introduction_ready"
    task_id: str
    greeting_message: str
    created_at: str


class PluginTwoTestRequest(BaseModel):
    company_name: str = ""
    hr_name: str = ""
    hr_title: str = ""
    job_name: str = ""
    match_score: int = Field(default=100, ge=0, le=100)
    greeting_message: str


class PluginTwoTaskResponse(BaseModel):
    success: bool
    task_id: str


class IntroductionGenerateResponse(BaseModel):
    success: bool
    task_id: str
    status: Literal["accepted"] = "accepted"
