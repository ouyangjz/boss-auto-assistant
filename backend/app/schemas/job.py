from typing import List

from pydantic import BaseModel, Field


class JobPayload(BaseModel):
    job_id: str = ""
    job_name: str = ""
    salary: str = ""
    location: str = ""
    experience: str = ""
    education: str = ""
    company_name: str = ""
    hr_name: str = ""
    hr_title: str = ""
    job_description: str = ""
    job_tags: List[str] = Field(default_factory=list)
    source_url: str = ""


class JobEvaluateResponse(BaseModel):
    success: bool
    match_score: int = Field(ge=0, le=100)

