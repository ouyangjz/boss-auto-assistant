from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    NOT_APPLIED = "未投递"
    CONTACTED = "沟通"
    RESUME_SENT = "投递简历"
    INTERVIEW = "面试阶段"
    ONBOARDING = "入职阶段"


class DashboardJobItem(BaseModel):
    id: int
    job_id: str
    job_name: str
    company_name: str
    hr_name: str
    hr_title: str
    match_score: Optional[int] = None
    status: ApplicationStatus
    created_at: datetime


class DashboardJobListResponse(BaseModel):
    items: List[DashboardJobItem]
    page: int
    page_size: int
    total: int


class DashboardRequirement(BaseModel):
    content: str
    importance: Optional[int] = None
    logic: Optional[str] = None
    alternatives: Any = None


class DashboardJobDetail(DashboardJobItem):
    salary: str
    location: str
    experience: str
    education: str
    job_description: str
    source_url: str
    tags: List[str] = Field(default_factory=list)
    updated_at: datetime
    job_category: str = ""
    summary: str = ""
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    top_requirements: List[DashboardRequirement] = Field(default_factory=list)
    self_intro_context: Any = None
    generated_introduction: Optional[str] = None


class DashboardStatusUpdate(BaseModel):
    status: ApplicationStatus


class DashboardStatusResponse(BaseModel):
    id: int
    status: ApplicationStatus
