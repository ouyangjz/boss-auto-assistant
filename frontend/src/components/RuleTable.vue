<script setup lang="ts">
import type { JobRule, RuleListName, RuleTarget } from '../api/management'

defineProps<{
  title: string
  description: string
  tone: 'danger' | 'success'
  listName: RuleListName
  rules: JobRule[]
  busyRuleId: string
}>()

defineEmits<{
  add: []
  edit: [rule: JobRule]
  remove: [rule: JobRule]
  toggle: [rule: JobRule, enabled: boolean]
}>()

const targetLabels: Record<RuleTarget, string> = {
  job_name: '岗位名称',
  company_name: '公司名称',
  job_description: '岗位描述',
  job_tags: '岗位标签',
}
</script>

<template>
  <article class="rule-panel" :class="`rule-panel--${tone}`">
    <header class="rule-panel__header">
      <div>
        <div class="rule-title-line">
          <span class="rule-tone-dot" />
          <h2>{{ title }}</h2>
          <el-tag size="small" effect="plain">{{ rules.length }}</el-tag>
        </div>
        <p>{{ description }}</p>
      </div>
      <el-button type="primary" plain @click="$emit('add')">＋ 添加规则</el-button>
    </header>

    <el-table v-if="rules.length" :data="rules" class="rule-table">
      <el-table-column label="规则" min-width="190">
        <template #default="{ row }: { row: JobRule }">
          <strong class="rule-keyword">{{ row.keyword }}</strong>
          <small v-if="row.match_type === 'exact'" class="legacy-badge">完全匹配</small>
        </template>
      </el-table-column>
      <el-table-column label="作用范围" min-width="120">
        <template #default="{ row }: { row: JobRule }">
          <span class="target-label">{{ targetLabels[row.target] }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="112">
        <template #default="{ row }: { row: JobRule }">
          <el-switch
            :model-value="row.enabled"
            :loading="busyRuleId === row.id"
            :aria-label="`${row.keyword}启用状态`"
            @change="$emit('toggle', row, Boolean($event))"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="132" align="right">
        <template #default="{ row }: { row: JobRule }">
          <el-button type="primary" link @click="$emit('edit', row)">编辑</el-button>
          <el-button type="danger" link @click="$emit('remove', row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-else class="rule-empty">
      <span>暂无规则</span>
      <small>添加第一条关键词规则后将立即参与岗位判断</small>
    </div>
  </article>
</template>

<style scoped>
.rule-panel { overflow: hidden; background: white; border: 1px solid var(--line); border-top: 3px solid #90a0b8; border-radius: 12px; }
.rule-panel--danger { border-top-color: #e45b5b; }
.rule-panel--success { border-top-color: #35a873; }
.rule-panel__header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; padding: 23px 25px 18px; border-bottom: 1px solid #edf0f4; }
.rule-title-line { display: flex; gap: 9px; align-items: center; }
.rule-title-line h2 { margin: 0; font-size: 17px; }
.rule-tone-dot { width: 7px; height: 7px; border-radius: 50%; background: #90a0b8; }
.rule-panel--danger .rule-tone-dot { background: #e45b5b; }
.rule-panel--success .rule-tone-dot { background: #35a873; }
.rule-panel__header p { margin: 7px 0 0 16px; color: var(--muted); font-size: 11px; }
.rule-table { width: 100%; }
.rule-keyword { display: inline-block; max-width: 220px; overflow: hidden; color: #263247; font-size: 13px; text-overflow: ellipsis; vertical-align: middle; white-space: nowrap; }
.legacy-badge { display: inline-block; margin-left: 7px; padding: 2px 5px; color: #7a8494; background: #f1f3f6; border-radius: 4px; font-size: 9px; vertical-align: middle; }
.target-label { color: #566174; font-size: 12px; }
.rule-empty { display: grid; min-height: 160px; place-content: center; text-align: center; color: #7c8798; }
.rule-empty small { margin-top: 7px; color: #a1a9b5; font-size: 10px; }
</style>
