import axios from 'axios'
import type {
  ApplicationStatus,
  JobDetail,
  JobFilters,
  JobListResponse,
} from '../types/job'

const client = axios.create({
  baseURL: '/api/v1/dashboard',
  timeout: 15_000,
})

export async function fetchJobs(filters: JobFilters): Promise<JobListResponse> {
  const { data } = await client.get<JobListResponse>('/jobs', { params: filters })
  return data
}

export async function fetchJob(jobId: number): Promise<JobDetail> {
  const { data } = await client.get<JobDetail>(`/jobs/${jobId}`)
  return data
}

export async function updateJobStatus(
  jobId: number,
  status: ApplicationStatus,
): Promise<{ id: number; status: ApplicationStatus }> {
  const { data } = await client.patch<{ id: number; status: ApplicationStatus }>(
    `/jobs/${jobId}/status`,
    { status },
  )
  return data
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail) return detail
    if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  }
  return fallback
}
