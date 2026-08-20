<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { fetchAnalysisOverview } from '../api/analysis'
import { getApiErrorMessage } from '../api/jobs'
import type { AnalysisOverview } from '../types/analysis'
import type { ApplicationStatus } from '../types/job'

const overview = ref<AnalysisOverview | null>(null)
const loading = ref(true)
const errorMessage = ref('')
let requestVersion = 0

const filters = reactive<{
  days: '' | 7 | 30
  jobCategory: string
  minScore: '' | number
  applicationStatus: '' | ApplicationStatus
}>({
  days: '',
  jobCategory: '',
  minScore: '',
  applicationStatus: '',
})

const summaryCards = computed(() => {
  const summary = overview.value?.summary
  return [
    { label: '岗位总数', value: summary?.total_jobs ?? 0, note: '当前筛选范围' },
    {
      label: '平均匹配度',
      value: summary?.average_match_score?.toFixed(1) ?? '--',
      note: '仅统计有效评分',
    },
    { label: '≥ 70 岗位', value: summary?.qualified_jobs ?? 0, note: '高匹配岗位' },
    { label: '已沟通', value: summary?.contacted_jobs ?? 0, note: '按实际求职状态' },
  ]
})

const maximumScoreBucket = computed(() =>
  Math.max(1, ...(overview.value?.match_score_distribution.map((item) => item.count) ?? [])),
)
const maximumCategoryCount = computed(() =>
  Math.max(1, ...(overview.value?.job_category_distribution.map((item) => item.count) ?? [])),
)
const maximumRequirementCount = computed(() =>
  Math.max(1, ...(overview.value?.top_requirements.map((item) => item.count) ?? [])),
)

function percent(value: number, maximum: number): string {
  return `${Math.max(0, Math.min(100, (value / maximum) * 100))}%`
}

async function loadOverview() {
  const version = ++requestVersion
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await fetchAnalysisOverview({
      days: filters.days || undefined,
      job_category: filters.jobCategory || undefined,
      min_score: filters.minScore === '' ? undefined : filters.minScore,
      application_status: filters.applicationStatus || undefined,
    })
    if (version === requestVersion) overview.value = result
  } catch (error) {
    if (version !== requestVersion) return
    overview.value = null
    errorMessage.value = getApiErrorMessage(error, '岗位分析数据加载失败，请稍后重试')
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <section class="page analysis-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">JOB ANALYSIS</p>
        <h1>岗位分析</h1>
        <p class="page-description">基于已采集岗位与最新 AI 评估结果，查看岗位结构和技能匹配情况。</p>
      </div>
      <div class="record-count">
        <strong>{{ overview?.summary.total_jobs ?? 0 }}</strong>
        <span>筛选结果</span>
      </div>
    </header>

    <div class="filter-bar analysis-filters">
      <el-select v-model="filters.days" aria-label="日期范围" @change="loadOverview">
        <el-option label="全部日期" value="" />
        <el-option label="最近 7 天" :value="7" />
        <el-option label="最近 30 天" :value="30" />
      </el-select>
      <el-select
        v-model="filters.jobCategory"
        aria-label="岗位类别"
        filterable
        @change="loadOverview"
      >
        <el-option label="全部类别" value="" />
        <el-option
          v-for="category in overview?.filter_options.job_categories ?? []"
          :key="category"
          :label="category"
          :value="category"
        />
      </el-select>
      <el-select v-model="filters.minScore" aria-label="最低匹配度" @change="loadOverview">
        <el-option label="全部匹配度" value="" />
        <el-option label="≥ 60 分" :value="60" />
        <el-option label="≥ 70 分" :value="70" />
        <el-option label="≥ 80 分" :value="80" />
      </el-select>
      <el-select
        v-model="filters.applicationStatus"
        aria-label="投递状态"
        @change="loadOverview"
      >
        <el-option label="全部状态" value="" />
        <el-option
          v-for="status in overview?.filter_options.application_statuses ?? []"
          :key="status"
          :label="status"
          :value="status"
        />
      </el-select>
    </div>

    <div v-if="loading" class="analysis-loading" aria-label="岗位分析加载中">
      <div class="summary-grid">
        <div v-for="index in 4" :key="index" class="analysis-card summary-card">
          <el-skeleton :rows="2" animated />
        </div>
      </div>
      <div class="analysis-card loading-panel"><el-skeleton :rows="8" animated /></div>
    </div>

    <el-alert
      v-else-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-button type="primary" link @click="loadOverview">重新加载</el-button>
      </template>
    </el-alert>

    <el-empty
      v-else-if="!overview || overview.summary.total_jobs === 0"
      description="当前筛选条件下暂无岗位数据"
      class="analysis-empty"
    />

    <template v-else>
      <div class="summary-grid">
        <article v-for="card in summaryCards" :key="card.label" class="analysis-card summary-card">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.note }}</small>
        </article>
      </div>

      <div class="analysis-grid two-columns">
        <article class="analysis-card chart-card">
          <div class="analysis-card-heading">
            <div><span>01</span><h2>匹配度分布</h2></div>
            <small>仅统计有效评分</small>
          </div>
          <div class="vertical-chart" aria-label="匹配度分布柱状图">
            <div
              v-for="bucket in overview.match_score_distribution"
              :key="bucket.range"
              class="vertical-bar-item"
            >
              <strong>{{ bucket.count }}</strong>
              <div class="vertical-track">
                <span :style="{ height: percent(bucket.count, maximumScoreBucket) }" />
              </div>
              <small>{{ bucket.range }}</small>
            </div>
          </div>
        </article>

        <article class="analysis-card chart-card">
          <div class="analysis-card-heading">
            <div><span>02</span><h2>岗位类型分布</h2></div>
            <small>Top 10</small>
          </div>
          <div v-if="overview.job_category_distribution.length" class="horizontal-chart">
            <div
              v-for="item in overview.job_category_distribution"
              :key="item.category"
              class="horizontal-bar-item"
            >
              <div class="bar-label">
                <span :title="item.category">{{ item.category }}</span><strong>{{ item.count }}</strong>
              </div>
              <div class="horizontal-track">
                <span :style="{ width: percent(item.count, maximumCategoryCount) }" />
              </div>
            </div>
          </div>
          <div v-else class="panel-empty">暂无岗位类别数据</div>
        </article>
      </div>

      <article class="analysis-card chart-card wide-card">
        <div class="analysis-card-heading">
          <div><span>03</span><h2>技能需求 Top 10</h2></div>
          <small>占当前岗位总数比例</small>
        </div>
        <div v-if="overview.top_required_skills.length" class="skill-chart">
          <div v-for="item in overview.top_required_skills" :key="item.skill" class="skill-row">
            <span class="skill-name">{{ item.skill }}</span>
            <div class="skill-track"><span :style="{ width: `${item.percentage}%` }" /></div>
            <strong>{{ item.count }}</strong>
            <small>{{ item.percentage.toFixed(1) }}%</small>
          </div>
        </div>
        <div v-else class="panel-empty">暂无技能需求数据</div>
      </article>

      <article class="analysis-card chart-card wide-card">
        <div class="analysis-card-heading">
          <div><span>04</span><h2>核心要求 Top 10</h2></div>
          <small>按出现岗位数排序</small>
        </div>
        <ol v-if="overview.top_requirements.length" class="requirement-ranking">
          <li v-for="(item, index) in overview.top_requirements" :key="item.requirement">
            <span class="rank-number">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="requirement-name">{{ item.requirement }}</span>
            <div class="ranking-track">
              <span :style="{ width: percent(item.count, maximumRequirementCount) }" />
            </div>
            <strong>{{ item.count }}</strong>
          </li>
        </ol>
        <div v-else class="panel-empty">暂无核心要求数据</div>
      </article>

      <div class="analysis-grid two-columns comparison-grid">
        <article class="analysis-card skill-comparison strength-card">
          <div class="analysis-card-heading">
            <div><span>05</span><h2>优势技能</h2></div>
            <small>Top 5</small>
          </div>
          <div v-if="overview.strength_skills.length" class="skill-chip-list">
            <div v-for="item in overview.strength_skills" :key="item.skill" class="skill-chip">
              <span>{{ item.skill }}</span><strong>{{ item.count }} 个岗位</strong>
            </div>
          </div>
          <div v-else class="panel-empty">暂无足够数据</div>
        </article>

        <article class="analysis-card skill-comparison gap-card">
          <div class="analysis-card-heading">
            <div><span>06</span><h2>技能缺口</h2></div>
            <small>Top 5</small>
          </div>
          <div v-if="overview.skill_gaps.length" class="skill-chip-list">
            <div v-for="item in overview.skill_gaps" :key="item.skill" class="skill-chip">
              <span>{{ item.skill }}</span><strong>{{ item.count }} 个岗位</strong>
            </div>
          </div>
          <div v-else class="panel-empty">暂无足够数据</div>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.analysis-filters { flex-wrap: wrap; }
.analysis-filters .el-select { flex: 1 1 180px; }
.analysis-loading { display: grid; gap: 18px; }
.analysis-card { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 18px; }
.summary-card { position: relative; min-height: 142px; padding: 24px; overflow: hidden; }
.summary-card::after { content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 100%; background: var(--brand); }
.summary-card > span { color: #697487; font-size: 13px; font-weight: 650; }
.summary-card > strong { display: block; margin: 13px 0 8px; color: var(--ink); font-size: 34px; line-height: 1; }
.summary-card > small { color: #9aa3b1; font-size: 11px; }
.loading-panel { padding: 28px; }
.analysis-empty { min-height: 420px; background: white; border: 1px solid var(--line); border-radius: 12px; }
.analysis-grid { display: grid; gap: 18px; margin-bottom: 18px; }
.two-columns { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.chart-card, .skill-comparison { padding: 25px 27px; }
.wide-card { margin-bottom: 18px; }
.analysis-card-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 26px; }
.analysis-card-heading > div { display: flex; align-items: center; gap: 10px; }
.analysis-card-heading span { color: var(--brand); font-family: ui-monospace, monospace; font-size: 10px; font-weight: 750; }
.analysis-card-heading h2 { margin: 0; color: var(--ink); font-size: 17px; }
.analysis-card-heading small { color: #929baa; font-size: 10px; }
.vertical-chart { display: flex; align-items: end; justify-content: space-around; gap: 13px; min-height: 235px; padding-top: 10px; }
.vertical-bar-item { display: grid; grid-template-rows: 22px 170px 22px; flex: 1; align-items: end; text-align: center; }
.vertical-bar-item strong { color: #596579; font-size: 12px; }
.vertical-track { position: relative; width: min(45px, 70%); height: 160px; margin: 0 auto; overflow: hidden; background: #f0f3f8; border-radius: 5px 5px 2px 2px; }
.vertical-track span { position: absolute; right: 0; bottom: 0; left: 0; min-height: 2px; background: linear-gradient(180deg, #6c96f8, var(--brand)); border-radius: inherit; transition: height .25s ease; }
.vertical-bar-item small { color: #7b8698; font-size: 10px; }
.horizontal-chart { display: grid; gap: 14px; }
.horizontal-bar-item { min-width: 0; }
.bar-label { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 6px; color: #586477; font-size: 11px; }
.bar-label span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-label strong { color: #364154; }
.horizontal-track, .skill-track, .ranking-track { height: 7px; overflow: hidden; background: #eef1f5; border-radius: 99px; }
.horizontal-track span, .skill-track span, .ranking-track span { display: block; height: 100%; background: #5e89ef; border-radius: inherit; }
.skill-chart { display: grid; gap: 14px; }
.skill-row { display: grid; grid-template-columns: 150px minmax(120px, 1fr) 40px 55px; gap: 13px; align-items: center; }
.skill-name { overflow: hidden; color: #465164; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.skill-row strong { color: #303c50; font-size: 12px; text-align: right; }
.skill-row small { color: #8a94a3; font-size: 10px; text-align: right; }
.requirement-ranking { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.requirement-ranking li { display: grid; grid-template-columns: 32px minmax(220px, 1.4fr) minmax(160px, 1fr) 38px; gap: 12px; align-items: center; min-height: 36px; }
.rank-number { color: #8691a2 !important; }
.requirement-name { overflow: hidden; color: #465164; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.requirement-ranking strong { color: #344055; font-size: 12px; text-align: right; }
.comparison-grid { margin-bottom: 0; }
.skill-comparison { min-height: 245px; }
.strength-card { border-top: 3px solid #40b883; }
.gap-card { border-top: 3px solid #e8a23b; }
.skill-chip-list { display: grid; gap: 9px; }
.skill-chip { display: flex; justify-content: space-between; gap: 16px; padding: 12px 14px; color: #344055; background: #f8fafc; border: 1px solid #edf0f4; border-radius: 8px; font-size: 12px; }
.skill-chip strong { color: #6f7a8c; font-size: 11px; font-weight: 600; }
.panel-empty { display: grid; min-height: 150px; place-items: center; color: #9aa3b1; font-size: 12px; }

@media (max-width: 1320px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .two-columns { grid-template-columns: 1fr; }
}
</style>
