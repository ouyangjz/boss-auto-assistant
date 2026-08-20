<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { JobRule, RuleInput, RuleTarget } from '../api/management'

const props = defineProps<{
  modelValue: boolean
  rule: JobRule | null
  listLabel: string
  saving: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [input: RuleInput]
}>()

const formRef = ref<FormInstance>()
const form = reactive<RuleInput>({
  keyword: '',
  target: 'job_name',
  match_type: 'contains',
  enabled: true,
})

const rules: FormRules<RuleInput> = {
  keyword: [
    { required: true, message: '请输入关键词', trigger: 'blur' },
    { min: 1, max: 120, message: '关键词最多 120 个字符', trigger: 'blur' },
  ],
  target: [{ required: true, message: '请选择匹配字段', trigger: 'change' }],
}

const targetOptions: Array<{ label: string; value: RuleTarget }> = [
  { label: '岗位名称', value: 'job_name' },
  { label: '公司名称', value: 'company_name' },
  { label: '岗位描述', value: 'job_description' },
  { label: '岗位标签', value: 'job_tags' },
]

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return
    form.keyword = props.rule?.keyword ?? ''
    form.target = props.rule?.target ?? 'job_name'
    form.match_type = props.rule?.match_type ?? 'contains'
    form.enabled = props.rule?.enabled ?? true
  },
)

async function submit() {
  if (!formRef.value || !(await formRef.value.validate().catch(() => false))) return
  emit('save', { ...form, keyword: form.keyword.trim() })
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="`${rule ? '编辑' : '添加'}${listLabel}规则`"
    width="480px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="关键词" prop="keyword">
        <el-input v-model="form.keyword" maxlength="120" show-word-limit placeholder="输入需要匹配的关键词" />
      </el-form-item>
      <el-form-item label="匹配字段" prop="target">
        <el-select v-model="form.target" style="width: 100%">
          <el-option v-for="item in targetOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="匹配方式">
        <el-input :model-value="form.match_type === 'exact' ? '完全匹配（兼容旧规则）' : '包含关键词'" disabled />
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="form.enabled" active-text="启用" inactive-text="禁用" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存规则</el-button>
    </template>
  </el-dialog>
</template>
