<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchJob, getApiErrorMessage, updateJobStatus } from '../api/jobs'
import StatusTag from '../components/StatusTag.vue'
import { APPLICATION_STATUSES } from '../types/job'
import type { ApplicationStatus, JobDetail } from '../types/job'

const route = useRoute()
const router = useRouter()
const job = ref<JobDetail | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const updatingStatus = ref(false)
const selectedStatus = ref<ApplicationStatus>('未投递')

const jobId = computed(() => Number(route.params.id))
const introSections = computed(() => {
  const context = job.value?.self_intro_context
  if (!Array.isArray(context)) return []
  const labels: Record<string, string> = {
    target_requirements: '岗位核心要求',
    relevant_experiences: '对应项目经验',
    matched_skills: '匹配技能',
    highlight_points: '亮点',
  }
  return context.flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    return Object.entries(item as Record<string, unknown>)
      .filter(([, value]) => value !== null && value !== '' && (!Array.isArray(value) || value.length))
      .map(([key, value]) => ({
        label: labels[key] ?? key.replace(/_/g, ' '),
        values: Array.isArray(value) ? value.map(String) : [String(value)],
      }))
  })
})

async function loadJob() {
  if (!Number.isInteger(jobId.value) || jobId.value < 1) {
    errorMessage.value = '岗位编号无效'
    loading.value = false
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    job.value = await fetchJob(jobId.value)
    selectedStatus.value = job.value.status
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '岗位详情加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function changeStatus(status: ApplicationStatus) {
  if (!job.value || status === job.value.status) return
  const previous = job.value.status
  updatingStatus.value = true
  try {
    const result = await updateJobStatus(job.value.id, status)
    job.value.status = result.status
    selectedStatus.value = result.status
    ElMessage.success('投递状态已更新')
  } catch (error) {
    selectedStatus.value = previous
    ElMessage.error(getApiErrorMessage(error, '投递状态更新失败，请重试'))
  } finally {
    updatingStatus.value = false
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

onMounted(loadJob)
</script>

<template>
  <section class="page detail-page">
    <button class="back-button" type="button" @click="router.push('/jobs')">
      <span aria-hidden="true">←</span> 返回投递总览
    </button>

    <div v-if="loading" class="detail-loading">
      <el-skeleton :rows="8" animated />
    </div>

    <el-alert
      v-else-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-button type="primary" link @click="loadJob">重新加载</el-button>
      </template>
    </el-alert>

    <template v-else-if="job">
      <header class="detail-hero">
        <div class="detail-title-block">
          <p class="eyebrow">JOB DETAIL · {{ job.job_id }}</p>
          <h1>{{ job.job_name || '未命名岗位' }}</h1>
          <p class="detail-company">{{ job.company_name || '未记录公司' }}</p>
          <div class="detail-badges">
            <span class="score-badge">匹配度 <strong>{{ job.match_score ?? '—' }}</strong></span>
            <StatusTag :status="job.status" />
          </div>
        </div>
        <div class="status-editor">
          <label for="status-select">投递状态</label>
          <el-select
            id="status-select"
            v-model="selectedStatus"
            :loading="updatingStatus"
            :disabled="updatingStatus"
            @change="changeStatus"
          >
            <el-option
              v-for="status in APPLICATION_STATUSES"
              :key="status"
              :label="status"
              :value="status"
            />
          </el-select>
          <span>修改成功后自动保存</span>
        </div>
      </header>

      <div class="detail-grid">
        <div class="detail-main">
          <section class="content-card">
            <div class="section-heading">
              <span class="section-number">01</span>
              <h2>基本信息</h2>
            </div>
            <dl class="info-grid">
              <div><dt>公司</dt><dd>{{ job.company_name || '—' }}</dd></div>
              <div><dt>薪资</dt><dd>{{ job.salary || '—' }}</dd></div>
              <div><dt>地点</dt><dd>{{ job.location || '—' }}</dd></div>
              <div><dt>经验</dt><dd>{{ job.experience || '—' }}</dd></div>
              <div><dt>学历</dt><dd>{{ job.education || '—' }}</dd></div>
              <div><dt>HR</dt><dd>{{ [job.hr_name, job.hr_title].filter(Boolean).join(' · ') || '—' }}</dd></div>
              <div><dt>采集时间</dt><dd>{{ formatDate(job.created_at) }}</dd></div>
              <div><dt>更新时间</dt><dd>{{ formatDate(job.updated_at) }}</dd></div>
            </dl>
            <div v-if="job.tags.length" class="tag-row">
              <el-tag v-for="tag in job.tags" :key="tag" effect="plain">{{ tag }}</el-tag>
            </div>
            <a v-if="job.source_url" class="source-link" :href="job.source_url" target="_blank" rel="noreferrer">
              查看 BOSS 原岗位 <span aria-hidden="true">↗</span>
            </a>
          </section>

          <section class="content-card">
            <div class="section-heading">
              <span class="section-number">02</span>
              <h2>岗位描述</h2>
            </div>
            <p v-if="job.job_description" class="job-description">{{ job.job_description }}</p>
            <el-empty v-else description="暂无岗位描述" :image-size="72" />
          </section>

          <section class="content-card">
            <div class="section-heading">
              <span class="section-number">03</span>
              <h2>岗位匹配分析</h2>
            </div>
            <p v-if="job.summary" class="analysis-summary">{{ job.summary }}</p>
            <div v-if="job.top_requirements.length" class="requirement-list">
              <div v-for="requirement in job.top_requirements" :key="requirement.content" class="requirement-item">
                <span>{{ requirement.content }}</span>
                <el-tag v-if="requirement.importance !== null" size="small" type="warning">
                  重要度 {{ requirement.importance }}
                </el-tag>
              </div>
            </div>
            <div v-if="job.required_skills.length || job.preferred_skills.length" class="skill-groups">
              <div v-if="job.required_skills.length">
                <h3>必备技能</h3>
                <div class="tag-row"><el-tag v-for="skill in job.required_skills" :key="skill">{{ skill }}</el-tag></div>
              </div>
              <div v-if="job.preferred_skills.length">
                <h3>加分技能</h3>
                <div class="tag-row"><el-tag v-for="skill in job.preferred_skills" :key="skill" type="success" effect="plain">{{ skill }}</el-tag></div>
              </div>
            </div>
            <el-empty
              v-if="!job.summary && !job.top_requirements.length && !job.required_skills.length && !job.preferred_skills.length"
              description="暂无匹配分析"
              :image-size="72"
            />
          </section>

          <section v-if="introSections.length" class="content-card">
            <div class="section-heading">
              <span class="section-number">04</span>
              <h2>自我介绍匹配依据</h2>
            </div>
            <div class="intro-grid">
              <div v-for="(section, index) in introSections" :key="`${section.label}-${index}`" class="intro-item">
                <h3>{{ section.label }}</h3>
                <ul><li v-for="value in section.values" :key="value">{{ value }}</li></ul>
              </div>
            </div>
          </section>

          <section v-if="job.generated_introduction" class="content-card introduction-card">
            <div class="section-heading">
              <span class="section-number">05</span>
              <h2>自动生成的自我介绍</h2>
            </div>
            <p>{{ job.generated_introduction }}</p>
          </section>
        </div>

        <aside class="detail-aside">
          <div class="aside-card">
            <span>当前匹配度</span>
            <strong>{{ job.match_score ?? '—' }}</strong>
            <div v-if="job.match_score !== null" class="score-track">
              <span :style="{ width: `${job.match_score}%` }" />
            </div>
            <small>{{ job.job_category || '暂无岗位分类' }}</small>
          </div>
        </aside>
      </div>
    </template>
  </section>
</template>
