export const APPLICATION_STATUSES = [
  '未投递',
  '沟通',
  '投递简历',
  '面试阶段',
  '入职阶段',
] as const

export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number]

export interface JobItem {
  id: number
  job_id: string
  job_name: string
  company_name: string
  hr_name: string
  hr_title: string
  match_score: number | null
  status: ApplicationStatus
  created_at: string
}

export interface JobRequirement {
  content: string
  importance: number | null
  logic: string | null
  alternatives: unknown
}

export interface JobDetail extends JobItem {
  salary: string
  location: string
  experience: string
  education: string
  job_description: string
  source_url: string
  tags: string[]
  updated_at: string
  job_category: string
  summary: string
  required_skills: string[]
  preferred_skills: string[]
  top_requirements: JobRequirement[]
  self_intro_context: unknown
  generated_introduction: string | null
}

export interface JobListResponse {
  items: JobItem[]
  page: number
  page_size: number
  total: number
}

export interface JobFilters {
  page: number
  page_size: number
  status?: ApplicationStatus
  min_score?: number
  keyword?: string
}
