<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { fetchJobs, getApiErrorMessage } from '../api/jobs'
import JobCard from '../components/JobCard.vue'
import { APPLICATION_STATUSES } from '../types/job'
import type { ApplicationStatus, JobItem } from '../types/job'

const jobs = ref<JobItem[]>([])
const total = ref(0)
const loading = ref(true)
const errorMessage = ref('')
let requestVersion = 0
let keywordTimer: ReturnType<typeof setTimeout> | undefined

const filters = reactive<{
  page: number
  pageSize: number
  status: '' | ApplicationStatus
  minScore: '' | number
  keyword: string
}>({
  page: 1,
  pageSize: 20,
  status: '',
  minScore: '',
  keyword: '',
})

async function loadJobs() {
  const version = ++requestVersion
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await fetchJobs({
      page: filters.page,
      page_size: filters.pageSize,
      status: filters.status || undefined,
      min_score: filters.minScore === '' ? undefined : filters.minScore,
      keyword: filters.keyword.trim() || undefined,
    })
    if (version !== requestVersion) return
    jobs.value = result.items
    total.value = result.total
  } catch (error) {
    if (version !== requestVersion) return
    jobs.value = []
    errorMessage.value = getApiErrorMessage(error, '岗位列表加载失败，请稍后重试')
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function applyImmediateFilter() {
  filters.page = 1
  loadJobs()
}

function onPageChange(page: number) {
  filters.page = page
  loadJobs()
}

watch(
  () => filters.keyword,
  () => {
    clearTimeout(keywordTimer)
    keywordTimer = setTimeout(applyImmediateFilter, 350)
  },
)

onMounted(loadJobs)
onBeforeUnmount(() => clearTimeout(keywordTimer))
</script>

<template>
  <section class="page page-overview">
    <header class="page-header">
      <div>
        <p class="eyebrow">APPLICATION PIPELINE</p>
        <h1>投递总览</h1>
        <p class="page-description">集中查看已采集岗位、匹配结果与当前求职进度。</p>
      </div>
      <div class="record-count">
        <strong>{{ total }}</strong>
        <span>岗位记录</span>
      </div>
    </header>

    <div class="filter-bar">
      <el-select
        v-model="filters.status"
        aria-label="投递状态"
        placeholder="投递状态"
        clearable
        @change="applyImmediateFilter"
      >
        <el-option label="全部状态" value="" />
        <el-option
          v-for="status in APPLICATION_STATUSES"
          :key="status"
          :label="status"
          :value="status"
        />
      </el-select>
      <el-select
        v-model="filters.minScore"
        aria-label="最低匹配度"
        placeholder="最低匹配度"
        clearable
        @change="applyImmediateFilter"
      >
        <el-option label="全部匹配度" value="" />
        <el-option label="≥ 60 分" :value="60" />
        <el-option label="≥ 70 分" :value="70" />
        <el-option label="≥ 80 分" :value="80" />
      </el-select>
      <el-input
        v-model="filters.keyword"
        class="keyword-input"
        clearable
        placeholder="搜索岗位或公司"
        aria-label="搜索岗位或公司"
      >
        <template #prefix>⌕</template>
      </el-input>
    </div>

    <div v-if="loading" class="job-grid" aria-label="岗位加载中">
      <div v-for="index in 6" :key="index" class="skeleton-card">
        <el-skeleton :rows="4" animated />
      </div>
    </div>

    <el-alert
      v-else-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-button type="primary" link @click="loadJobs">重新加载</el-button>
      </template>
    </el-alert>

    <el-empty v-else-if="jobs.length === 0" description="当前暂无岗位记录" />

    <template v-else>
      <div class="job-grid">
        <JobCard v-for="job in jobs" :key="job.id" :job="job" />
      </div>
      <div class="pagination-wrap">
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page="filters.page"
          :page-size="filters.pageSize"
          :total="total"
          @current-change="onPageChange"
        />
      </div>
    </template>
  </section>
</template>
