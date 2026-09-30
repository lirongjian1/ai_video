<script setup lang="ts">
import { Delete, Edit, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onActivated, reactive, ref, watch } from 'vue'

import { errorMessage, http } from '@/api/http'
import type { AiFile, Character, PageResult, Project, Prompt, Scene } from '@/types'

const props = defineProps<{ entityType: 'characters' | 'scenes' }>()
type Entity = Character | Scene
const isCharacter = computed(() => props.entityType === 'characters')
const labels = computed(() => isCharacter.value
  ? { title: '角色管理', noun: '角色', detail1: '外观设定', detail2: '性格设定', placeholder1: '服装、发型、年龄、体态等', placeholder2: '性格、语气、行为习惯等' }
  : { title: '场景管理', noun: '场景', detail1: '环境设定', detail2: '氛围设定', placeholder1: '地点、时间、天气、陈设等', placeholder2: '光线、色调、情绪等' })
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const items = ref<Entity[]>([])
const projects = ref<Project[]>([])
const prompts = ref<Prompt[]>([])
const images = ref<AiFile[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', projectId: null as number | null, page: 1, pageSize: 20 })
const form = reactive({ project_id: null as number | null, name: '', description: '', detail1: '', detail2: '', reference_file_id: null as number | null, prompt_id: null as number | null, status: 'ACTIVE' as 'ACTIVE' | 'DISABLED' })

function projectName(id: number) { return projects.value.find((item) => item.id === id)?.name || `项目 #${id}` }
function detail1(item: Entity) { return isCharacter.value ? (item as Character).appearance : (item as Scene).environment }

async function loadOptions() {
  const promptType = isCharacter.value ? 'CHARACTER' : 'SCENE'
  const [projectResult, promptResult, imageResult] = await Promise.all([
    http.get<PageResult<Project>>('/projects', { params: { page_size: 100 } }),
    http.get<PageResult<Prompt>>('/prompts', { params: { prompt_type: promptType, page_size: 100 } }),
    http.get<PageResult<AiFile>>('/files', { params: { file_type: 'IMAGE', page_size: 100 } }),
  ])
  projects.value = projectResult.data.items
  prompts.value = promptResult.data.items
  images.value = imageResult.data.items
}

async function loadData() {
  loading.value = true
  try {
    const { data } = await http.get<PageResult<Entity>>(`/${props.entityType}`, { params: { keyword: filters.keyword || undefined, project_id: filters.projectId || undefined, page: filters.page, page_size: filters.pageSize } })
    items.value = data.items
    total.value = data.total
    await loadOptions()
  } catch (error) { ElMessage.error(errorMessage(error, `${labels.value.noun}加载失败`)) } finally { loading.value = false }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { project_id: filters.projectId, name: '', description: '', detail1: '', detail2: '', reference_file_id: null, prompt_id: null, status: 'ACTIVE' })
  dialogVisible.value = true
}

function openEdit(item: Entity) {
  editingId.value = item.id
  const character = item as Character
  const scene = item as Scene
  Object.assign(form, { project_id: item.project_id, name: item.name, description: item.description || '', detail1: (isCharacter.value ? character.appearance : scene.environment) || '', detail2: (isCharacter.value ? character.personality : scene.atmosphere) || '', reference_file_id: item.reference_file_id, prompt_id: item.prompt_id, status: item.status })
  dialogVisible.value = true
}

async function save() {
  if (!form.project_id || !form.name.trim()) return ElMessage.warning(`请选择项目并填写${labels.value.noun}名称`)
  const payload: Record<string, unknown> = { project_id: form.project_id, name: form.name.trim(), description: form.description.trim() || null, reference_file_id: form.reference_file_id, prompt_id: form.prompt_id, status: form.status }
  if (isCharacter.value) Object.assign(payload, { appearance: form.detail1.trim() || null, personality: form.detail2.trim() || null })
  else Object.assign(payload, { environment: form.detail1.trim() || null, atmosphere: form.detail2.trim() || null })
  saving.value = true
  try {
    if (editingId.value) await http.put(`/${props.entityType}/${editingId.value}`, payload)
    else await http.post(`/${props.entityType}`, payload)
    ElMessage.success(editingId.value ? `${labels.value.noun}已更新` : `${labels.value.noun}已创建`)
    dialogVisible.value = false
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { saving.value = false }
}

async function remove(item: Entity) {
  try {
    await ElMessageBox.confirm(`确定删除${labels.value.noun}“${item.name}”吗？`, `删除${labels.value.noun}`, { type: 'warning' })
    await http.delete(`/${props.entityType}/${item.id}`)
    ElMessage.success(`${labels.value.noun}已删除`)
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

function search() { filters.page = 1; loadData() }
watch(() => props.entityType, () => { filters.page = 1; loadData() })
onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header"><div><h1>{{ labels.title }}</h1><p>维护项目中的{{ labels.noun }}设定、参考图与提示词关联</p></div><div class="page-actions"><el-button type="primary" :icon="Plus" @click="openCreate">新建{{ labels.noun }}</el-button></div></div>
    <div class="filter-bar"><el-input v-model="filters.keyword" clearable :placeholder="`搜索${labels.noun}名称或描述`" style="width: 260px" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="filters.projectId" clearable placeholder="全部项目" style="width: 180px" @change="search"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-button @click="search">查询</el-button></div>
    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="items" :empty-text="`暂无${labels.noun}`">
        <el-table-column prop="name" :label="`${labels.noun}名称`" min-width="180" />
        <el-table-column label="归属项目" min-width="160"><template #default="{ row }">{{ projectName(row.project_id) }}</template></el-table-column>
        <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip><template #default="{ row }"><span :class="{ muted: !row.description }">{{ row.description || '暂无描述' }}</span></template></el-table-column>
        <el-table-column :label="labels.detail1" min-width="220" show-overflow-tooltip><template #default="{ row }"><span :class="{ muted: !detail1(row) }">{{ detail1(row) || '未设置' }}</span></template></el-table-column>
        <el-table-column label="参考图" width="85"><template #default="{ row }"><el-image v-if="row.reference_file_id && images.find((item) => item.id === row.reference_file_id)" :src="images.find((item) => item.id === row.reference_file_id)?.url" fit="cover" class="reference-thumb" :preview-src-list="[images.find((item) => item.id === row.reference_file_id)?.url || '']" preview-teleported /><span v-else class="muted">无</span></template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" effect="plain">{{ row.status === 'ACTIVE' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData" /></div>
    </section>
    <el-dialog v-model="dialogVisible" :title="`${editingId ? '编辑' : '新建'}${labels.noun}`" width="min(700px, calc(100vw - 32px))">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="归属项目" required><el-select v-model="form.project_id" placeholder="请选择项目" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item :label="`${labels.noun}名称`" required><el-input v-model="form.name" maxlength="150" /></el-form-item></div>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        <div class="form-grid"><el-form-item :label="labels.detail1"><el-input v-model="form.detail1" type="textarea" :rows="4" :placeholder="labels.placeholder1" /></el-form-item><el-form-item :label="labels.detail2"><el-input v-model="form.detail2" type="textarea" :rows="4" :placeholder="labels.placeholder2" /></el-form-item></div>
        <div class="form-grid"><el-form-item label="参考图"><el-select v-model="form.reference_file_id" clearable filterable placeholder="从图片库选择" style="width: 100%"><el-option v-for="item in images" :key="item.id" :label="item.file_name" :value="item.id" /></el-select></el-form-item><el-form-item label="提示词"><el-select v-model="form.prompt_id" clearable filterable placeholder="关联提示词" style="width: 100%"><el-option v-for="item in prompts" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div>
        <el-form-item label="状态"><el-segmented v-model="form.status" :options="[{ label: '启用', value: 'ACTIVE' }, { label: '停用', value: 'DISABLED' }]" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; } .reference-thumb { width: 42px; height: 42px; border-radius: 4px; } @media (max-width: 620px) { .form-grid { grid-template-columns: 1fr; gap: 0; } }</style>
