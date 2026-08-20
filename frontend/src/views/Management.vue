<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createRule,
  deleteRule,
  fetchManagementConfig,
  saveManagementSettings,
  testRules,
  updateRule,
} from '../api/management'
import type {
  JobRule,
  ManagementConfig,
  RuleInput,
  RuleListName,
  RuleTestResult,
} from '../api/management'
import { getApiErrorMessage } from '../api/jobs'
import RuleEditor from '../components/RuleEditor.vue'
import RuleTable from '../components/RuleTable.vue'

const config = ref<ManagementConfig | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const savingSettings = ref(false)
const editorVisible = ref(false)
const editorSaving = ref(false)
const editingRule = ref<JobRule | null>(null)
const editingList = ref<RuleListName>('blacklist')
const busyRuleId = ref('')
const threshold = ref(70)
const testing = ref(false)
const testResult = ref<RuleTestResult | null>(null)

const testInput = reactive({
  job_name: '',
  company_name: '',
  job_description: '',
})

const enabledRuleCount = computed(() => {
  if (!config.value) return 0
  return [...config.value.blacklist, ...config.value.whitelist].filter((rule) => rule.enabled).length
})

const editorListLabel = computed(() => (editingList.value === 'blacklist' ? '黑名单' : '白名单'))

async function loadConfig() {
  loading.value = true
  errorMessage.value = ''
  try {
    config.value = await fetchManagementConfig()
    threshold.value = config.value.settings.match_threshold
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '规则配置加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  if (!Number.isInteger(threshold.value) || threshold.value < 0 || threshold.value > 100) {
    ElMessage.error('匹配阈值必须是 0 到 100 的整数')
    return
  }
  savingSettings.value = true
  try {
    const saved = await saveManagementSettings(threshold.value)
    if (config.value) config.value.settings = saved
    ElMessage.success('配置已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存失败，请重试'))
  } finally {
    savingSettings.value = false
  }
}

function openEditor(listName: RuleListName, rule: JobRule | null = null) {
  editingList.value = listName
  editingRule.value = rule
  editorVisible.value = true
}

function replaceRule(listName: RuleListName, saved: JobRule) {
  if (!config.value) return
  const list = config.value[listName]
  const index = list.findIndex((rule) => rule.id === saved.id)
  if (index >= 0) list[index] = saved
  else list.push(saved)
}

async function saveRule(input: RuleInput) {
  editorSaving.value = true
  try {
    const saved = editingRule.value
      ? await updateRule(editingList.value, editingRule.value.id, input)
      : await createRule(editingList.value, input)
    replaceRule(editingList.value, saved)
    editorVisible.value = false
    ElMessage.success('配置已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存失败，请重试'))
  } finally {
    editorSaving.value = false
  }
}

async function toggleRule(listName: RuleListName, rule: JobRule, enabled: boolean) {
  busyRuleId.value = rule.id
  try {
    replaceRule(listName, await updateRule(listName, rule.id, { enabled }))
    ElMessage.success(enabled ? '规则已启用' : '规则已禁用')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存失败，请重试'))
  } finally {
    busyRuleId.value = ''
  }
}

async function removeRule(listName: RuleListName, rule: JobRule) {
  try {
    await ElMessageBox.confirm(
      `删除后该规则将立即停止生效。`,
      `确定删除规则“${rule.keyword}”吗？`,
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  busyRuleId.value = rule.id
  try {
    await deleteRule(listName, rule.id)
    if (config.value) {
      config.value[listName] = config.value[listName].filter((item) => item.id !== rule.id)
    }
    ElMessage.success('规则已删除')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '删除失败，请重试'))
  } finally {
    busyRuleId.value = ''
  }
}

async function runRuleTest() {
  if (!testInput.job_name.trim() && !testInput.company_name.trim() && !testInput.job_description.trim()) {
    ElMessage.warning('请至少填写一项岗位信息')
    return
  }
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testRules({ ...testInput })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '规则测试失败，请重试'))
  } finally {
    testing.value = false
  }
}

onMounted(loadConfig)
</script>

<template>
  <section class="page management-page">
    <header class="page-header management-header">
      <div>
        <p class="eyebrow">RULE MANAGEMENT</p>
        <h1>规则配置</h1>
        <p class="page-description">维护自动求职的本地过滤规则与匹配阈值，保存后对下一岗位立即生效。</p>
      </div>
      <div class="rule-summary">
        <div><strong>{{ enabledRuleCount }}</strong><span>启用规则</span></div>
        <div><strong>{{ config?.settings.match_threshold ?? '—' }}</strong><span>当前阈值</span></div>
      </div>
    </header>

    <div v-if="loading" class="management-loading">
      <div v-for="index in 3" :key="index" class="management-skeleton"><el-skeleton :rows="4" animated /></div>
    </div>

    <el-alert v-else-if="errorMessage" :title="errorMessage" type="error" :closable="false" show-icon>
      <template #default><el-button type="primary" link @click="loadConfig">重新加载</el-button></template>
    </el-alert>

    <template v-else-if="config">
      <div class="settings-grid">
        <article class="settings-card threshold-card">
          <div class="card-kicker">基础设置</div>
          <div class="settings-heading">
            <div>
              <h2>自动沟通匹配阈值</h2>
              <p>Coze 匹配度达到该值后，岗位才会进入自动沟通流程。</p>
            </div>
            <span class="live-badge"><i /> 实时生效</span>
          </div>
          <div class="threshold-control">
            <el-input-number v-model="threshold" :min="0" :max="100" :step="1" controls-position="right" />
            <span class="threshold-unit">/ 100</span>
            <el-button type="primary" :loading="savingSettings" @click="saveSettings">保存设置</el-button>
          </div>
          <div class="threshold-scale">
            <span :style="{ width: `${threshold}%` }" />
          </div>
          <div class="scale-labels"><span>宽松 0</span><span>严格 100</span></div>
        </article>

      </div>

      <div class="rules-grid">
        <RuleTable
          title="黑名单规则"
          description="优先判断；命中后跳过 Coze 和自动沟通"
          tone="danger"
          list-name="blacklist"
          :rules="config.blacklist"
          :busy-rule-id="busyRuleId"
          @add="openEditor('blacklist')"
          @edit="openEditor('blacklist', $event)"
          @remove="removeRule('blacklist', $event)"
          @toggle="(rule, enabled) => toggleRule('blacklist', rule, enabled)"
        />
        <RuleTable
          title="白名单规则"
          description="未命中黑名单时判断；命中后按本地规则直接通过"
          tone="success"
          list-name="whitelist"
          :rules="config.whitelist"
          :busy-rule-id="busyRuleId"
          @add="openEditor('whitelist')"
          @edit="openEditor('whitelist', $event)"
          @remove="removeRule('whitelist', $event)"
          @toggle="(rule, enabled) => toggleRule('whitelist', rule, enabled)"
        />
      </div>

      <article class="rule-test-card">
        <div class="rule-test-heading">
          <div><span class="card-kicker">规则测试</span><h2>验证本地判断结果</h2></div>
          <p>只运行本地黑白名单，不调用 Coze，也不会保存岗位。</p>
        </div>
        <div class="test-form">
          <el-input v-model="testInput.job_name" placeholder="岗位名称" aria-label="测试岗位名称" />
          <el-input v-model="testInput.company_name" placeholder="公司名称" aria-label="测试公司名称" />
          <el-input v-model="testInput.job_description" placeholder="岗位描述中的关键词" aria-label="测试岗位描述" />
          <el-button type="primary" :loading="testing" @click="runRuleTest">测试规则</el-button>
        </div>
        <div v-if="testResult" class="test-result" :class="`test-result--${testResult.result}`">
          <strong>
            {{ testResult.result === 'blacklist' ? '黑名单命中' : testResult.result === 'whitelist' ? '白名单命中' : '未命中本地规则' }}
          </strong>
          <span v-if="testResult.matched_rule">{{ testResult.matched_rule.keyword }} · {{ testResult.matched_rule.target }}</span>
          <span v-else>该岗位将继续进入 Coze 分析</span>
        </div>
      </article>
    </template>

    <RuleEditor
      v-model="editorVisible"
      :rule="editingRule"
      :list-label="editorListLabel"
      :saving="editorSaving"
      @save="saveRule"
    />
  </section>
</template>

<style scoped>
.management-header { align-items: center; }
.rule-summary { display: flex; gap: 28px; padding: 15px 20px; background: white; border: 1px solid var(--line); border-radius: 11px; }
.rule-summary div { display: grid; gap: 4px; min-width: 78px; }
.rule-summary div + div { padding-left: 25px; border-left: 1px solid var(--line); }
.rule-summary strong { color: var(--ink); font-size: 23px; line-height: 1; }
.rule-summary span { color: #8a94a4; font-size: 10px; }
.management-loading { display: grid; gap: 18px; }
.management-skeleton { padding: 26px; background: white; border: 1px solid var(--line); border-radius: 12px; }
.settings-grid { margin-bottom: 18px; }
.settings-card, .rule-test-card { padding: 25px 27px; background: white; border: 1px solid var(--line); border-radius: 12px; }
.card-kicker { margin-bottom: 12px; color: var(--brand); font-size: 10px; font-weight: 750; letter-spacing: .13em; text-transform: uppercase; }
.settings-heading { display: flex; justify-content: space-between; gap: 22px; align-items: flex-start; }
.settings-card h2, .rule-test-card h2 { margin: 0; color: var(--ink); font-size: 17px; }
.settings-heading p { margin: 7px 0 0; color: var(--muted); font-size: 11px; }
.live-badge { display: inline-flex; gap: 6px; align-items: center; padding: 6px 9px; color: #21835c; background: #ecf8f2; border-radius: 99px; font-size: 10px; white-space: nowrap; }
.live-badge i { width: 6px; height: 6px; background: #35b77b; border-radius: 50%; }
.threshold-control { display: flex; gap: 10px; align-items: center; margin-top: 25px; }
.threshold-control .el-input-number { width: 150px; }
.threshold-control .el-button { margin-left: auto; }
.threshold-unit { color: #8b95a4; font-size: 12px; }
.threshold-scale { height: 5px; margin-top: 24px; overflow: hidden; background: #edf1f6; border-radius: 99px; }
.threshold-scale span { display: block; height: 100%; background: linear-gradient(90deg, #80a6fb, var(--brand)); border-radius: inherit; transition: width .2s ease; }
.scale-labels { display: flex; justify-content: space-between; margin-top: 6px; color: #a0a8b4; font-size: 9px; }
.rules-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-bottom: 18px; align-items: start; }
.rule-test-card { padding-bottom: 24px; }
.rule-test-heading { display: flex; justify-content: space-between; align-items: end; gap: 24px; margin-bottom: 18px; }
.rule-test-heading .card-kicker { margin-bottom: 8px; }
.rule-test-heading p { margin: 0; color: #8b95a5; font-size: 10px; }
.test-form { display: grid; grid-template-columns: 1fr 1fr 1.3fr auto; gap: 10px; }
.test-result { display: flex; gap: 12px; align-items: center; margin-top: 15px; padding: 12px 14px; color: #5e6878; background: #f5f7fa; border-left: 3px solid #8b96a8; border-radius: 7px; font-size: 11px; }
.test-result strong { color: #384457; }
.test-result--blacklist { background: #fff4f3; border-left-color: #df5e5e; }
.test-result--whitelist { background: #edf9f3; border-left-color: #35a873; }

@media (max-width: 1380px) {
  .rules-grid { grid-template-columns: 1fr; }
  .test-form { grid-template-columns: 1fr 1fr; }
}
</style>
