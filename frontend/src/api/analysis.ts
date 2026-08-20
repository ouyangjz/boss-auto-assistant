import axios from 'axios'
import type { AnalysisFilters, AnalysisOverview } from '../types/analysis'

const client = axios.create({
  baseURL: '/api/v1/analysis',
  timeout: 15_000,
})

export async function fetchAnalysisOverview(
  filters: AnalysisFilters,
): Promise<AnalysisOverview> {
  const { data } = await client.get<AnalysisOverview>('/overview', { params: filters })
  return data
}
