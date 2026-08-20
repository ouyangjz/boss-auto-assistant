import type { ApplicationStatus } from './job'

export interface AnalysisSummary {
  total_jobs: number
  average_match_score: number | null
  qualified_jobs: number
  contacted_jobs: number
}

export interface MatchScoreBucket {
  range: string
  count: number
}

export interface JobCategoryCount {
  category: string
  count: number
}

export interface SkillFrequency {
  skill: string
  count: number
  percentage: number
}

export interface RequirementFrequency {
  requirement: string
  count: number
}

export interface SkillCount {
  skill: string
  count: number
}

export interface AnalysisFilterOptions {
  job_categories: string[]
  application_statuses: ApplicationStatus[]
}

export interface AnalysisOverview {
  summary: AnalysisSummary
  match_score_distribution: MatchScoreBucket[]
  job_category_distribution: JobCategoryCount[]
  top_required_skills: SkillFrequency[]
  top_requirements: RequirementFrequency[]
  strength_skills: SkillCount[]
  skill_gaps: SkillCount[]
  filter_options: AnalysisFilterOptions
}

export interface AnalysisFilters {
  days?: 7 | 30
  job_category?: string
  min_score?: number
  application_status?: ApplicationStatus
}
