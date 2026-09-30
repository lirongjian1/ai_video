<script setup lang="ts">
import { Delete, DocumentCopy, Edit, MagicStick, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onActivated, reactive, ref } from 'vue'

import { errorMessage, http } from '@/api/http'
import type { ModelConfig, PageResult, Project, Prompt } from '@/types'

const promptTypes = [
  { label: '角色', value: 'CHARACTER' }, { label: '场景', value: 'SCENE' },
  { label: '剧本', value: 'SCRIPT' }, { label: '分镜', value: 'STORYBOARD' },
  { label: '视频', value: 'VIDEO' }, { label: '自定义', value: 'CUSTOM' },
]
const typeLabel = Object.fromEntries(promptTypes.map((item) => [item.value, item.label]))
const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const dialogVisible = ref(false)
const generateVisible = ref(false)
const editingId = ref<number | null>(null)
const prompts = ref<Prompt[]>([])
const projects = ref<Project[]>([])
const textModels = ref<ModelConfig[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', projectId: null as number | null, promptType: '', page: 1, pageSize: 20 })
const form = reactive({
  project_id: null as number | null,
  name: '', prompt_type: 'CUSTOM' as Prompt['prompt_type'], content: '', negative_prompt: '',
  variablesText: '{}', status: 'ENABLED' as Prompt['status'],
})
const generateForm = reactive({ project_id: null as number | null, name: '', generation_type: 'CHARACTER_THREE_VIEW', keywords: '', model_config_id: null as number | null })

function projectName(id: number | null) {
  return id ? projects.value.find((item) => item.id === id)?.name || `项目 #${id}` : '公共模板'
}

async function loadData() {
  loading.value = true
  try {
    const [promptResult, projectResult, modelResult] = await Promise.all([
      http.get<PageResult<Prompt>>('/prompts', { params: { keyword: filters.keyword || undefined, project_id: filters.projectId || undefined, prompt_type: filters.promptType || undefined, page: filters.page, page_size: filters.pageSize } }),
      http.get<PageResult<Project>>('/projects', { params: { page_size: 100 } }),
      http.get<PageResult<ModelConfig>>('/model-configs', { params: { model_type: 'TEXT', status: 'ENABLED', page_size: 100 } }),
    ])
    prompts.value = promptResult.data.items
    total.value = promptResult.data.total
    projects.value = projectResult.data.items
    textModels.value = modelResult.data.items
  } catch (error) {
    ElMessage.error(errorMessage(error, '提示词加载失败'))
  } finally { loading.value = false }
}

function openGenerate() {
  const defaultModel = textModels.value.find((item) => item.is_default) || textModels.value[0]
  Object.assign(generateForm, { project_id: filters.projectId, name: '', generation_type: 'CHARACTER_THREE_VIEW', keywords: '', model_config_id: defaultModel?.id || null })
  generateVisible.value = true
}

async function generatePrompt() {
  if (!generateForm.name.trim() || !generateForm.keywords.trim() || !generateForm.model_config_id) return ElMessage.warning('请填写名称、关键内容并选择文本模型')
  generating.value = true
  try {
    await http.post('/prompts/generate', { ...generateForm, name: generateForm.name.trim(), keywords: generateForm.keywords.trim() }, { timeout: 180000 })
    ElMessage.success('提示词生成完成')
    generateVisible.value = false
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error, '提示词生成失败')) } finally { generating.value = false }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { project_id: null, name: '', prompt_type: 'CUSTOM', content: '', negative_prompt: '', variablesText: '{}', status: 'ENABLED' })
  dialogVisible.value = true
}

function openEdit(item: Prompt) {
  editingId.value = item.id
  Object.assign(form, { project_id: item.project_id, name: item.name, prompt_type: item.prompt_type, content: item.content, negative_prompt: item.negative_prompt || '', variablesText: JSON.stringify(item.variables, null, 2), status: item.status })
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim() || !form.content.trim()) return ElMessage.warning('请填写名称和提示词内容')
  let variables: Record<string, unknown>
  try { variables = JSON.parse(form.variablesText || '{}') as Record<string, unknown> } catch { return ElMessage.warning('变量配置必须是有效的 JSON 对象') }
  if (Array.isArray(variables) || typeof variables !== 'object' || variables === null) return ElMessage.warning('变量配置必须是 JSON 对象')
  saving.value = true
  try {
    const payload = { project_id: form.project_id, name: form.name.trim(), prompt_type: form.prompt_type, content: form.content.trim(), negative_prompt: form.negative_prompt.trim() || null, variables, status: form.status }
    if (editingId.value) await http.put(`/prompts/${editingId.value}`, payload)
    else await http.post('/prompts', payload)
    ElMessage.success(editingId.value ? '提示词已更新' : '提示词已创建')
    dialogVisible.value = false
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { saving.value = false }
}

async function remove(item: Prompt) {
  try {
    await ElMessageBox.confirm(`确定删除“${item.name}”吗？`, '删除提示词', { type: 'warning' })
    await http.delete(`/prompts/${item.id}`)
    ElMessage.success('提示词已删除')
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

function fallbackCopy(content: string) {
  const textarea = document.createElement('textarea')
  textarea.value = content
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand('copy')
  textarea.remove()
  if (!copied) throw new Error('copy failed')
}

async function copyContent(content: string) {
  if (!content.trim()) return ElMessage.warning('暂无可复制的提示词内容')
  let copied = false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(content)
        copied = true
      } catch { /* Continue with the compatibility fallback. */ }
    }
    try {
      fallbackCopy(content)
      copied = true
    } catch { /* The Clipboard API may already have succeeded. */ }
    if (!copied) throw new Error('copy failed')
    ElMessage.success('完整提示词已复制')
  } catch {
    ElMessage.error('复制失败，请在编辑窗口中手动选择内容')
  }
}

function search() { filters.page = 1; loadData() }
onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header"><div><h1>提示词管理</h1><p>维护可复用的角色、场景、剧本与视频提示模板</p></div><div class="page-actions"><el-button :icon="Plus" @click="openCreate">手动新建</el-button><el-button type="primary" :icon="MagicStick" @click="openGenerate">AI 生成提示词</el-button></div></div>
    <div class="filter-bar">
      <el-input v-model="filters.keyword" clearable placeholder="搜索名称或内容" style="width: 250px" :prefix-icon="Search" @keyup.enter="search" />
      <el-select v-model="filters.projectId" clearable placeholder="全部项目" style="width: 180px" @change="search"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select>
      <el-select v-model="filters.promptType" clearable placeholder="全部类型" style="width: 140px" @change="search"><el-option v-for="item in promptTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select>
      <el-button @click="search">查询</el-button>
    </div>
    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="prompts" empty-text="暂无提示词">
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column label="类型" width="100"><template #default="{ row }"><el-tag effect="plain">{{ typeLabel[row.prompt_type] }}</el-tag></template></el-table-column>
        <el-table-column label="归属项目" min-width="150"><template #default="{ row }">{{ projectName(row.project_id) }}</template></el-table-column>
        <el-table-column prop="content" label="提示词内容" min-width="300" show-overflow-tooltip />
        <el-table-column label="状态" width="95"><template #default="{ row }"><el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" effect="plain">{{ row.status === 'ENABLED' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="更新时间" width="180"><template #default="{ row }">{{ new Date(row.updated_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" width="215" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="DocumentCopy" @click="copyContent(row.content)">复制</el-button><el-button text type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData" /></div>
    </section>
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑提示词' : '新建提示词'" width="min(720px, calc(100vw - 32px))">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="名称" required><el-input v-model="form.name" maxlength="150" /></el-form-item><el-form-item label="类型" required><el-select v-model="form.prompt_type" style="width: 100%"><el-option v-for="item in promptTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div>
        <div class="form-grid"><el-form-item label="归属项目"><el-select v-model="form.project_id" clearable placeholder="公共模板" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="状态"><el-segmented v-model="form.status" :options="[{ label: '启用', value: 'ENABLED' }, { label: '停用', value: 'DISABLED' }]" /></el-form-item></div>
        <el-form-item required><template #label><div class="field-label"><span>提示词内容</span><el-button text type="primary" :icon="DocumentCopy" @click="copyContent(form.content)">复制内容</el-button></div></template><el-input v-model="form.content" type="textarea" :rows="6" /></el-form-item>
        <el-form-item label="反向提示词"><el-input v-model="form.negative_prompt" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="变量配置（JSON）"><el-input v-model="form.variablesText" type="textarea" :rows="3" class="mono" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="generateVisible" title="AI 生成提示词" width="min(640px, calc(100vw - 32px))">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="提示词名称" required><el-input v-model="generateForm.name" maxlength="150" /></el-form-item><el-form-item label="生成类型" required><el-select v-model="generateForm.generation_type" style="width: 100%"><el-option label="主体定妆三视图" value="CHARACTER_THREE_VIEW" /><el-option label="场景概念图" value="SCENE" /></el-select></el-form-item></div>
        <div class="form-grid"><el-form-item label="归属项目"><el-select v-model="generateForm.project_id" clearable placeholder="公共模板" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="文本模型" required><el-select v-model="generateForm.model_config_id" placeholder="请选择文本模型" style="width: 100%"><el-option v-for="item in textModels" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div>
        <el-form-item label="关键内容" required><el-input v-model="generateForm.keywords" type="textarea" :rows="6" maxlength="5000" show-word-limit placeholder="输入主体外形、服装、风格，或场景地点、时间、氛围等关键描述" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="generateVisible = false">取消</el-button><el-button type="primary" :icon="MagicStick" :loading="generating" @click="generatePrompt">生成并保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.field-label { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.field-label :deep(.el-button) { height: 22px; padding: 0; }
@media (max-width: 620px) { .form-grid { grid-template-columns: 1fr; gap: 0; } }
</style>
