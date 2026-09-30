<script setup lang="ts">
import { Connection, Delete, Edit, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onActivated, reactive, ref } from 'vue'

import { errorMessage, modelConfigsApi, secretsApi } from '@/api'
import type { ApiSecret, ModelConfig } from '@/types'

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
const secrets = ref<ApiSecret[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', modelType: '', status: '', page: 1, pageSize: 20 })
const form = reactive({ name: '', model_type: 'TEXT' as ModelConfig['model_type'], video_protocol: 'COMFYUI', provider: '', base_url: '', model_name: '', secret_ref: '', extraConfigText: '{}', status: 'ENABLED' as ModelConfig['status'], is_default: false })

async function loadData() {
  loading.value = true
  try {
    const result = await modelConfigsApi.list({ keyword: filters.keyword || undefined, model_type: filters.modelType || undefined, status: filters.status || undefined, page: filters.page, page_size: filters.pageSize })
    items.value = result.items
    total.value = result.total
  } catch (error) { ElMessage.error(errorMessage(error, '模型配置加载失败')) } finally { loading.value = false }
}

/** 拉取密钥列表填充下拉框；失败不阻塞页面。 */
async function loadSecrets() {
  try { secrets.value = await secretsApi.list() } catch { secrets.value = [] }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', model_type: 'TEXT', video_protocol: 'COMFYUI', provider: '', base_url: '', model_name: '', secret_ref: '', extraConfigText: '{}', status: 'ENABLED', is_default: false })
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
  Object.assign(form, { name: item.name, model_type: item.model_type, video_protocol: inferVideoProtocol(item), provider: item.provider, base_url: item.base_url || '', model_name: item.model_name, secret_ref: item.secret_ref || '', extraConfigText: JSON.stringify(item.extra_config, null, 2), status: item.status, is_default: item.is_default })
  dialogVisible.value = true
}

function applyVideoProtocol(protocol = form.video_protocol) {
  if (protocol !== 'COMFYUI') return
  if (!form.provider || form.provider === 'AutoDL') form.provider = 'AutoDL ComfyUI'
  if (!form.base_url || form.base_url.includes('/contents/generations/tasks')) form.base_url = 'https://autodl.art/api/v1/comfyui/comfyui_workflow'
  if (form.extraConfigText.trim() === '{}') form.extraConfigText = JSON.stringify({ video_options: { resolution: '768p竖' }, reference_field_template: 'ref_image_{index}', poll_interval: 3 }, null, 2)
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
    const payload = { name: form.name.trim(), model_type: form.model_type, provider: form.provider.trim(), base_url: form.base_url.trim() || null, model_name: form.model_name.trim(), secret_ref: form.secret_ref.trim() || null, extra_config, status: form.status, is_default: form.is_default }
    if (editingId.value) await modelConfigsApi.update(editingId.value, payload)
    else await modelConfigsApi.create(payload)
    ElMessage.success(editingId.value ? '模型配置已更新' : '模型配置已创建')
    dialogVisible.value = false
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { saving.value = false }
}

async function remove(item: ModelConfig) {
  try {
    await ElMessageBox.confirm(`确定删除“${item.name}”吗？`, '删除模型配置', { type: 'warning' })
    await modelConfigsApi.remove(item.id)
    ElMessage.success('模型配置已删除')
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

async function testConnection(item: ModelConfig) {
  testingId.value = item.id
  try {
    const result = await modelConfigsApi.test(item.id)
    ElMessage.success(result.message)
  } catch (error) { ElMessage.error(errorMessage(error, '连接测试失败')) } finally { testingId.value = null }
}

/** 从已加载的密钥列表里找到引用名对应的掩码，用于表格展示。 */
const secretMasks = () => new Map(secrets.value.map((item) => [item.secret_ref, item.masked || '已配置']))

function search() { filters.page = 1; loadData() }
onActivated(() => { loadData(); loadSecrets() })
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
        <el-table-column label="密钥" min-width="190" show-overflow-tooltip><template #default="{ row }"><span v-if="row.secret_ref" class="secret-cell"><code class="mono-inline">{{ secretMasks().get(row.secret_ref) || row.secret_ref }}</code></span><span v-else class="muted">未配置</span></template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" effect="plain">{{ row.status === 'ENABLED' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="230" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="Connection" :loading="testingId === row.id" @click="testConnection(row)">测试</el-button><el-button text :icon="Edit" @click="openEdit(row)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData" /></div>
    </section>
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模型配置' : '新建模型配置'" width="min(720px, calc(100vw - 32px))">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="配置名称" required><el-input v-model="form.name" /></el-form-item><el-form-item label="模型类型" required><el-select v-model="form.model_type" style="width: 100%" @change="changeModelType"><el-option v-for="item in modelTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div>
        <el-form-item v-if="form.model_type === 'VIDEO'" label="视频接口协议" required><el-select v-model="form.video_protocol" style="width: 100%" @change="applyVideoProtocol"><el-option v-for="item in videoProtocols" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <div class="form-grid"><el-form-item label="厂商" required><el-input v-model="form.provider" :placeholder="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? 'AutoDL ComfyUI' : '例如 OpenAI Compatible'" /></el-form-item><el-form-item :label="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? '工作流 ID' : '模型名称'" required><el-input v-model="form.model_name" :placeholder="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? '例如 minimax_h3_image_audio_to_video_v2_15s' : '厂商提供的模型 ID'" /></el-form-item></div>
        <el-form-item :label="form.model_type === 'VIDEO' ? '任务提交地址' : '接口地址'"><el-input v-model="form.base_url" :placeholder="form.model_type === 'VIDEO' && form.video_protocol === 'COMFYUI' ? 'https://autodl.art/api/v1/comfyui/comfyui_workflow' : 'https://api.example.com/v1'" /></el-form-item>
        <el-form-item label="密钥">
          <el-select v-model="form.secret_ref" clearable filterable placeholder="选择要使用的密钥" style="width: 100%">
            <el-option v-for="item in secrets" :key="item.id" :label="`${item.name}（${item.masked || item.secret_ref}）`" :value="item.secret_ref" />
          </el-select>
          <div class="field-tip">密钥在「密钥管理」页面维护，此处只需选择引用名。</div>
        </el-form-item>
        <el-form-item label="扩展参数（JSON）"><el-input v-model="form.extraConfigText" type="textarea" :rows="4" class="mono" /></el-form-item>
        <div class="form-grid"><el-form-item label="状态"><el-segmented v-model="form.status" :options="[{ label: '启用', value: 'ENABLED' }, { label: '停用', value: 'DISABLED' }]" /></el-form-item><el-form-item label="默认模型"><el-switch v-model="form.is_default" active-text="设为该类型默认模型" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>.default-tag { margin-left: 8px; } .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; } .mono-inline { padding: 1px 6px; background: #f2f5f3; border-radius: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #6a716c; } .field-tip { margin-top: 4px; color: #8a918c; font-size: 12px; line-height: 1.5; } @media (max-width: 620px) { .form-grid { grid-template-columns: 1fr; gap: 0; } }</style>
