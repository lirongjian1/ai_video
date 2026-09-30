<script setup lang="ts">
import { Delete, Edit, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onActivated, reactive, ref } from 'vue'

import { errorMessage, http } from '@/api/http'
import type { PageResult, Project } from '@/types'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const projects = ref<Project[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', status: '', page: 1, pageSize: 20 })
const form = reactive({ name: '', description: '', status: 'ACTIVE' as Project['status'] })

async function loadProjects() {
  loading.value = true
  try {
    const { data } = await http.get<PageResult<Project>>('/projects', {
      params: {
        keyword: filters.keyword || undefined,
        status: filters.status || undefined,
        page: filters.page,
        page_size: filters.pageSize,
      },
    })
    projects.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '项目加载失败'))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', description: '', status: 'ACTIVE' })
  dialogVisible.value = true
}

function openEdit(project: Project) {
  editingId.value = project.id
  Object.assign(form, {
    name: project.name,
    description: project.description || '',
    status: project.status,
  })
  dialogVisible.value = true
}

async function saveProject() {
  if (!form.name.trim()) return ElMessage.warning('请输入项目名称')
  saving.value = true
  try {
    const payload = { ...form, name: form.name.trim(), description: form.description.trim() || null }
    if (editingId.value) await http.put(`/projects/${editingId.value}`, payload)
    else await http.post('/projects', payload)
    ElMessage.success(editingId.value ? '项目已更新' : '项目已创建')
    dialogVisible.value = false
    await loadProjects()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function removeProject(project: Project) {
  try {
    await ElMessageBox.confirm(`确定删除项目“${project.name}”吗？`, '删除项目', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await http.delete(`/projects/${project.id}`)
    ElMessage.success('项目已删除')
    await loadProjects()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error))
  }
}

function search() {
  filters.page = 1
  loadProjects()
}

onActivated(loadProjects)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div><h1>项目管理</h1><p>组织角色、场景、剧本、分镜与视频资产</p></div>
      <div class="page-actions"><el-button type="primary" :icon="Plus" @click="openCreate">新建项目</el-button></div>
    </div>

    <div class="filter-bar">
      <el-input v-model="filters.keyword" clearable placeholder="搜索项目名称或描述" style="width: 280px" :prefix-icon="Search" @keyup.enter="search" />
      <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 150px" @change="search">
        <el-option label="进行中" value="ACTIVE" />
        <el-option label="已归档" value="ARCHIVED" />
        <el-option label="已停用" value="DISABLED" />
      </el-select>
      <el-button @click="search">查询</el-button>
    </div>

    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="projects" empty-text="暂无项目">
        <el-table-column prop="name" label="项目名称" min-width="220" />
        <el-table-column prop="description" label="描述" min-width="300" show-overflow-tooltip>
          <template #default="{ row }"><span :class="{ muted: !row.description }">{{ row.description || '暂无描述' }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : row.status === 'ARCHIVED' ? 'info' : 'danger'" effect="plain">
              {{ row.status === 'ACTIVE' ? '进行中' : row.status === 'ARCHIVED' ? '已归档' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ new Date(row.updated_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button text type="danger" :icon="Delete" @click="removeProject(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-row">
        <el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadProjects" />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑项目' : '新建项目'" width="min(520px, calc(100vw - 32px))">
      <el-form label-position="top">
        <el-form-item label="项目名称" required><el-input v-model="form.name" maxlength="150" show-word-limit /></el-form-item>
        <el-form-item label="项目描述"><el-input v-model="form.description" type="textarea" :rows="4" maxlength="5000" /></el-form-item>
        <el-form-item label="状态">
          <el-segmented v-model="form.status" :options="[{ label: '进行中', value: 'ACTIVE' }, { label: '已归档', value: 'ARCHIVED' }, { label: '已停用', value: 'DISABLED' }]" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveProject">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

