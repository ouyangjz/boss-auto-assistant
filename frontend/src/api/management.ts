import axios from 'axios'

export type RuleListName = 'blacklist' | 'whitelist'
export type RuleTarget = 'job_name' | 'company_name' | 'job_description' | 'job_tags'
export type RuleMatchType = 'contains' | 'exact'

export interface JobRule {
  id: string
  keyword: string
  target: RuleTarget
  match_type: RuleMatchType
  enabled: boolean
}

export interface RuleInput {
  keyword: string
  target: RuleTarget
  match_type: RuleMatchType
  enabled: boolean
}

export interface ManagementConfig {
  version: number
  settings: { match_threshold: number }
  blacklist: JobRule[]
  whitelist: JobRule[]
}

export interface RuleTestInput {
  job_name: string
  company_name: string
  job_description: string
}

export interface RuleTestResult {
  result: RuleListName | 'unmatched'
  matched_rule: JobRule | null
}

const client = axios.create({
  baseURL: '/api/v1/management',
  timeout: 15_000,
})

export async function fetchManagementConfig(): Promise<ManagementConfig> {
  const { data } = await client.get<ManagementConfig>('/config')
  return data
}

export async function saveManagementSettings(matchThreshold: number) {
  const { data } = await client.patch<{ match_threshold: number }>('/settings', {
    match_threshold: matchThreshold,
  })
  return data
}

export async function createRule(listName: RuleListName, input: RuleInput) {
  const { data } = await client.post<JobRule>(`/${listName}`, input)
  return data
}

export async function updateRule(
  listName: RuleListName,
  ruleId: string,
  input: Partial<RuleInput>,
) {
  const { data } = await client.patch<JobRule>(`/${listName}/${ruleId}`, input)
  return data
}

export async function deleteRule(listName: RuleListName, ruleId: string) {
  await client.delete(`/${listName}/${ruleId}`)
}

export async function testRules(input: RuleTestInput) {
  const { data } = await client.post<RuleTestResult>('/test', input)
  return data
}
