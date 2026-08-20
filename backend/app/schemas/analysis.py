from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.dashboard import ApplicationStatus


class AnalysisSummary(BaseModel):
    total_jobs: int = 0
    average_match_score: Optional[float] = None
    qualified_jobs: int = 0
    contacted_jobs: int = 0


class MatchScoreBucket(BaseModel):
    range: str
    count: int = 0


class JobCategoryCount(BaseModel):
    category: str
    count: int


class SkillFrequency(BaseModel):
    skill: str
    count: int
    percentage: float


class RequirementFrequency(BaseModel):
    requirement: str
    count: int


class SkillCount(BaseModel):
    skill: str
    count: int


class AnalysisFilterOptions(BaseModel):
    job_categories: List[str] = Field(default_factory=list)
    application_statuses: List[ApplicationStatus] = Field(default_factory=list)


class AnalysisOverviewResponse(BaseModel):
    summary: AnalysisSummary = Field(default_factory=AnalysisSummary)
    match_score_distribution: List[MatchScoreBucket] = Field(default_factory=list)
    job_category_distribution: List[JobCategoryCount] = Field(default_factory=list)
    top_required_skills: List[SkillFrequency] = Field(default_factory=list)
    top_requirements: List[RequirementFrequency] = Field(default_factory=list)
    strength_skills: List[SkillCount] = Field(default_factory=list)
    skill_gaps: List[SkillCount] = Field(default_factory=list)
    filter_options: AnalysisFilterOptions = Field(default_factory=AnalysisFilterOptions)
