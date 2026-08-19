<script setup lang="ts">
import { computed } from 'vue'
import type { ApplicationStatus } from '../types/job'

const props = defineProps<{ status: ApplicationStatus }>()

const labels: Record<ApplicationStatus, string> = {
  未投递: '未投递',
  沟通: '已沟通',
  投递简历: '已投递',
  面试阶段: '面试中',
  入职阶段: '已入职',
}

const classes: Record<ApplicationStatus, string> = {
  未投递: 'neutral',
  沟通: 'primary',
  投递简历: 'success',
  面试阶段: 'warning',
  入职阶段: 'purple',
}

const label = computed(() => labels[props.status])
const colorClass = computed(() => classes[props.status])
</script>

<template>
  <span class="status-tag" :class="colorClass">
    <span class="status-dot" />
    {{ label }}
  </span>
</template>
