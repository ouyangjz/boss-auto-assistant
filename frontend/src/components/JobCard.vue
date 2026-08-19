<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { JobItem } from '../types/job'
import StatusTag from './StatusTag.vue'

const props = defineProps<{ job: JobItem }>()
const router = useRouter()

function openDetail() {
  router.push({ name: 'job-detail', params: { id: props.job.id } })
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}
</script>

<template>
  <article
    class="job-card"
    role="link"
    tabindex="0"
    :aria-label="`查看 ${job.job_name} 岗位详情`"
    @click="openDetail"
    @keydown.enter="openDetail"
    @keydown.space.prevent="openDetail"
  >
    <div class="job-card-topline">
      <div class="score" :class="{ muted: job.match_score === null }">
        <strong>{{ job.match_score ?? '—' }}</strong>
        <span>匹配度</span>
      </div>
      <StatusTag :status="job.status" />
    </div>

    <h2>{{ job.job_name || '未命名岗位' }}</h2>
    <p class="company">{{ job.company_name || '未记录公司' }}</p>

    <div class="job-meta">
      <span v-if="job.hr_name">HR · {{ job.hr_name }}</span>
      <span v-if="job.hr_title">{{ job.hr_title }}</span>
      <span v-if="!job.hr_name && !job.hr_title">HR 信息暂未记录</span>
    </div>

    <div class="job-card-footer">
      <span>采集于 {{ formatDate(job.created_at) }}</span>
      <span class="detail-link">查看详情 <span aria-hidden="true">→</span></span>
    </div>
  </article>
</template>
