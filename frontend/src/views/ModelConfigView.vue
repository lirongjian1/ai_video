<script setup lang="ts">
import { Connection, Delete, Edit, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onActivated, reactive, ref } from 'vue'

import { errorMessage, http } from '@/api/http'
import type { ModelConfig, PageResult } from '@/types'

const modelTypes = [{ label: '文本', value: 'TEXT' }, { label: '图片', value: 'IMAGE' }, { label: '视频', value: 'VIDEO' }]
const videoProtocols = [
  { label: 'AutoDL ComfyUI 工作流', value: 'COMFYUI' },
  { label: 'MiniMax 原生异步接口', value: 'MINIMAX' },
  { label: '火山方舟异步接口', value: 'ARK' },
  { label: '通用异步接口', value: 'GENERIC' },
]
const typeLabel = Object.fromEntries(modelTypes.map((item) => [item.value, item.label]))
const loading = ref(false)
const saving = ref(false)
const testingId = ref<number | null>(null)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const items = ref<ModelConfig[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', modelType: '', status: '', page: 1, pageSize: 20 })
const form = reactive({ name: '', model_type: 'TEXT' as ModelConfig['model_type'], video_protocol: 'COMFYUI', provider: '', base_url: '', model_name: '', api_key: '', api_key_env: '', extraConfigText: '{}', status: 'ENABLED' as ModelConfig['status'], is_default: false })

async function loadData() {
  loading.value = true
  try {
    const { data } = await http.get<PageResult<ModelConfig>>('/model-configs', { params: { keyword: filters.keyword || undefined, model_type: filters.modelType || undefined, status: filters.status || undefined, page: filters.page, page_size: filters.pageSize } })
    items.value = data.items
    total.value = data.total
  } catch (error) { ElMessage.error(errorMessage(error, '模型配置加载失败')) } finally { loading.value = false }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', model_type: 'TEXT', video_protocol: 'COMFYUI', provider: '', base_url: '', model_name: '', api_key: '', api_key_env: '', extraConfigText: '{}', status: 'ENABLED', is_default: false })
  dialogVisible.value = true
}

function inferVideoProtocol(item: ModelConfig) {
  const configured = String(item.extra_config.protocol || '').toUpperCase()
  if (videoProtocols.some((option) => option.value === configured)) return configured
  const url = (item.base_url || '').toLowerCase()
  if (url.includes('/comfyui/comfyui_workflow')) return 'COMFYUI'
  if (url.includes('/contents/generations/tasks')) return 'ARK'
  if (url.includes('/minimax/') || url.endsWith('/video_generation')) return 'MINIMAX'
  return 'GENERIC'
}

function openEdit(item: ModelConfig) {
  editingId.value = item.id
  Object.assign(form, { name: item.name, model_type: item.model_type, video_protocol: inferVideoProtocol(item), provider: item.provider, base_url: item.base_url || '', model_name: item.model_name, api_key: '', api_key_env: '', extraConfigText: JSON.stringify(item.extra_config, null, 2), status: item.status, is_default: item.is_default })
  dialogVisible.value = true
}

function applyVideoProtocol(protocol = form.video_protocol) {
  if (protocol !== 'COMFYUI') return
  if (!form.provider || form.provider === 'AutoDL') form.provider = 'AutoDL ComfyUI'
  if (!form.base_url || form.base_url.includes('/contents/generations/tasks')) form.base_url = 'https://autodl.art/api/v1/comfyui/comfyui_workflow'
  if (form.extraConfigText.trim() === '{}') form.extraConfigText = JSON.stringify({ video_options: { resolution: '768p竖' }, poll_interval: 3 }, null, 2)
}

function changeModelType(value: ModelConfig['model_type']) {
  if (value === 'VIDEO') applyVideoProtocol()
}

async function save() {
  if (!form.name.trim() || !form.provider.trim() || !form.model_name.trim()) return ElMessage.warning('请填写配置名称、厂商和模型名称')
  if (/^https?:\/\//i.test(form.model_name.trim())) return ElMessage.warning('模型名称应填写模型 ID，接口地址请填写在“接口地址”一栏')
  let extra_config: Record<string, unknown>
  try { extra_config = JSON.parse(form.extraConfigText || '{}') as Record<string, unknown> } catch { return ElMessage.warning('扩展参数必须是有效的 JSON 对象') }
  if (Array.isArray(extra_config) || typeof extra_config !== 'object' || extra_config === null) return ElMessage.warning('扩展参数必须是 JSON 对象')
  if (form.model_type === 'VIDEO') extra_config.protocol = form.video_protocol
  else delete extra_config.protocol
  saving.value = true
  try {
    const payload = { name: form.name.trim(), model_type: form.model_type, provider: form.provider.trim(), base_url: form.base_url.trim() || null, model_name: form.model_name.trim(), api_key: form.api_key.trim() || undefined, api_key_env: form.api_key_env.trim() || undefined, extra_config, status: form.status, is_default: form.is_default }
    if (editingId.value) await http.put(`/model-configs/${editingId.value}`, payload)
    else await http.post('/model-configs', payload)
    ElMessage.success(editingId.value ? '模型配置已更新' : '模型配置已创建')
    dialogVisible.value = false
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { saving.value = false }
}

async function remove(item: ModelConfig) {
  try {
    await ElMessageBox.confirm(`确定删除“${item.name}”吗？`, '删除模型配置', { type: 'warning' })
    await http.delete(`/model-configs/${item.id}`)
    ElMessage.success('模型配置已删除')
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

async function testConnection(item: ModelConfig) {
  testingId.value = item.id
  try {
    const { data } = await http.post<{ ok: boolean; message: string }>(`/model-configs/${item.id}/test`)
    ElMessage.success(data.message)
  } catch (error) { ElMessage.error(errorMessage(error, '连接测试失败')) } finally { testingId.value = null }
}

function search() { filters.page = 1; loadData() }
onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header"><div><h1>模型管理</h1><p>集中维护文本、图片与视频模型的连接参数</p></div><div class="page-actions"><el-button type="primary" :icon="Plus" @click="openCreate">新建配置</el-button></div></div>
    <div class="filter-bar"><el-input v-model="filters.keyword" clearable placeholder="搜索配置或模型名称" style="width: 260px" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="filters.modelType" clearable placeholder="全部类型" style="width: 130px" @change="search"><el-option v-for="item in modelTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select><el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 130px" @change="search"><el-option label="启用" value="ENABLED" /><el-option label="停用" value="DISABLED" /></el-select><el-button @click="search">查询</el-button></div>
    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="items" empty-text="暂无模型配置">
        <el-table-column prop="name" label="配置名称" min-width="180"><template #default="{ row }"><span>{{ row.name }}</span><el-tag v-if="row.is_default" size="small" type="success" effect="plain" class="default-tag">默认</el-tag></template></el-table-column>
        <el-table-column label="类型" width="90"><template #default="{ row }">{{ typeLabel[row.model_type] }}</template></el-table-column>
        <el-table-column prop="provider" label="厂商" min-width="150" />
        <el-table-column prop="model_name" label="模型名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="base_url" label="接口地址" min-width="240" show-overflow-tooltip><template #default="{ row }"><span :class="{ muted: !row.base_url }">{{ row.base_url || '使用厂商默认地址' }}</span></template></el-table-column>
        <el-table-column label="Key" width="120"><template #default="{ row }"><span :class="{ muted: !row.has_api_key }">{{ row.api_key_masked || '未配置' }}</span></template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" effect="plain">{{ row.status === 'ENABLED' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="230" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="Connection" :loading="testingId === row.id" @click="testConnection(row)">测试</el-button><el-button text :icon="Edit" @click="openEdit(row)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData" /></div>
    </section>
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模型配置' : '新建模型配置'" width="min(720px, calc(100vw - 32px))">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="配置名称" required><el-input v-model="form.name" /></el-form-item><el-form-item label="模型类型" required><el-select v-model="form.model_type" style="width: 100%" @change="changeModelType"><el-option v-for="item in modelTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div>
        <el-form-item v-if="form.model_type === 'VIDEO'" label="视频接口协议" required><el-select v-model="form.video_protocol" style="width: 100%" @change="applyVideoProtocol"><el-option v-for="item in videoProtocols" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <div class="form-grid"><el-form-item label="厂商" required><el-input v-model="form.provider" :placeholder="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? 'AutoDL ComfyUI' : '例如 OpenAI Compatible'" /></el-form-item><el-form-item :label="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? '工作流 ID' : '模型名称'" required><el-input v-model="form.model_name" :placeholder="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? '例如 minimax_h3_lightx2v_no_pic' : '厂商提供的模型 ID'" /></el-form-item></div>
        <el-form-item :label="form.model_type === 'VIDEO' ? '任务提交地址' : '接口地址'"><el-input v-model="form.base_url" :placeholder="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? 'https://autodl.art/api/v1/comfyui/comfyui_workflow' : 'https://api.example.com/v1'" /></el-form-item>
        <el-form-item :label="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? 'ComfyUI Token' : 'API Key'"><el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" :placeholder="editingId ? '留空则保留当前 Key' : '输入模型服务 API Key'" /></el-form-item>
        <el-form-item label="API Key 环境变量"><el-input v-model="form.api_key_env" placeholder="可选，例如 OPENAI_API_KEY" /></el-form-item>
        <el-form-item label="扩展参数（JSON）"><el-input v-model="form.extraConfigText" type="textarea" :rows="4" class="mono" /></el-form-item>
        <div class="form-grid"><el-form-item label="状态"><el-segmented v-model="form.status" :options="[{ label: '启用', value: 'ENABLED' }, { label: '停用', value: 'DISABLED' }]" /></el-form-item><el-form-item label="默认模型"><el-switch v-model="form.is_default" active-text="设为该类型默认模型" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>.default-tag { margin-left: 8px; } .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; } @media (max-width: 620px) { .form-grid { grid-template-columns: 1fr; gap: 0; } }</style>
