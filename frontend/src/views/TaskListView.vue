<script setup lang="ts">
import { CircleClose, Delete, RefreshRight, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onActivated, onDeactivated, reactive, ref } from 'vue'

import { errorMessage, projectsApi, tasksApi } from '@/api'
import type { AiTask, Project } from '@/types'

const typeLabels: Record<AiTask['task_type'], string> = { TEXT: '文本生成', IMAGE: '图片生成', VIDEO: '视频生成', MERGE: '视频合成' }
const statusLabels: Record<AiTask['status'], string> = { PENDING: '等待中', RUNNING: '执行中', SUCCESS: '成功', FAILED: '失败', CANCELLED: '已取消' }
const loading = ref(false)
const items = ref<AiTask[]>([])
const projects = ref<Project[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', projectId: null as number | null, taskType: '', status: '', page: 1, pageSize: 20 })
let refreshTimer: ReturnType<typeof setInterval> | null = null

function projectName(id: number | null) { return id ? projects.value.find((item) => item.id === id)?.name || `项目 #${id}` : '未归属项目' }
function tagType(status: AiTask['status']) { return status === 'SUCCESS' ? 'success' : status === 'FAILED' ? 'danger' : status === 'RUNNING' ? 'warning' : 'info' }
function providerTaskId(item: AiTask) { return String(item.provider_task_id || item.result_payload?.provider_task_id || '') }
function providerStatus(item: AiTask) { return String(item.provider_status || item.result_payload?.provider_status || '') }

async function loadData(silent = false) {
  if (!silent) loading.value = true
  try {
    const [taskResult, projectResult] = await Promise.all([
      tasksApi.list({ keyword: filters.keyword || undefined, project_id: filters.projectId || undefined, task_type: filters.taskType || undefined, status: filters.status || undefined, page: filters.page, page_size: filters.pageSize }),
      projectsApi.list({ page_size: 100 }),
    ])
    items.value = taskResult.items
    total.value = taskResult.total
    projects.value = projectResult.items
  } catch (error) { if (!silent) ElMessage.error(errorMessage(error, '任务加载失败')) } finally { loading.value = false }
}

async function cancel(item: AiTask) {
  try {
    await ElMessageBox.confirm(`确定取消任务“${item.name}”吗？`, '取消任务', { type: 'warning' })
    await tasksApi.cancel(item.id)
    ElMessage.success('任务已取消')
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}
async function remove(item: AiTask) {
  try {
    await ElMessageBox.confirm(`确定删除任务记录“${item.name}”吗？`, '删除任务', { type: 'warning' })
    await tasksApi.remove(item.id)
    ElMessage.success('任务记录已删除')
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}
function search() { filters.page = 1; loadData() }
onActivated(() => { loadData(); refreshTimer = setInterval(() => loadData(true), 5000) })
onDeactivated(() => { if (refreshTimer) clearInterval(refreshTimer); refreshTimer = null })
</script>

<template>
  <div class="page">
    <div class="page-header"><div><h1>视频任务</h1><p>查看生成与合成任务的状态、进度和错误信息</p></div><div class="page-actions"><el-button :icon="RefreshRight" @click="loadData()">刷新</el-button></div></div>
    <div class="filter-bar"><el-input v-model="filters.keyword" clearable placeholder="搜索任务名称" style="width: 230px" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="filters.projectId" clearable placeholder="全部项目" style="width: 170px" @change="search"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-select v-model="filters.taskType" clearable placeholder="全部类型" style="width: 140px" @change="search"><el-option label="文本生成" value="TEXT" /><el-option label="图片生成" value="IMAGE" /><el-option label="视频生成" value="VIDEO" /><el-option label="视频合成" value="MERGE" /></el-select><el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 130px" @change="search"><el-option label="等待中" value="PENDING" /><el-option label="执行中" value="RUNNING" /><el-option label="成功" value="SUCCESS" /><el-option label="失败" value="FAILED" /><el-option label="已取消" value="CANCELLED" /></el-select><el-button @click="search">查询</el-button></div>
    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="items" empty-text="暂无任务">
        <el-table-column prop="name" label="任务名称" min-width="200" />
        <el-table-column label="类型" width="110"><template #default="{ row }">{{ typeLabels[row.task_type as AiTask['task_type']] }}</template></el-table-column>
        <el-table-column label="归属项目" min-width="150"><template #default="{ row }">{{ projectName(row.project_id) }}</template></el-table-column>
        <el-table-column label="平台任务" min-width="190"><template #default="{ row }"><template v-if="providerTaskId(row)"><el-tooltip :content="providerTaskId(row)" placement="top"><span class="provider-task-id">{{ providerTaskId(row) }}</span></el-tooltip><span v-if="providerStatus(row)" class="provider-task-status">{{ providerStatus(row) }}</span></template><span v-else class="muted-text">-</span></template></el-table-column>
        <el-table-column label="进度" min-width="180"><template #default="{ row }"><el-progress :percentage="row.progress" :status="row.status === 'SUCCESS' ? 'success' : row.status === 'FAILED' ? 'exception' : undefined" /></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tooltip :content="row.error_message || ''" :disabled="!row.error_message" placement="top"><el-tag :type="tagType(row.status)" effect="plain">{{ statusLabels[row.status as AiTask['status']] }}</el-tag></el-tooltip></template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" width="145" fixed="right"><template #default="{ row }"><el-button v-if="['PENDING', 'RUNNING'].includes(row.status)" text type="warning" :icon="CircleClose" @click="cancel(row)">取消</el-button><el-button v-else text type="danger" :icon="Delete" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData()" /></div>
    </section>
  </div>
</template>

<style scoped>
.provider-task-id {
  display: block;
  max-width: 165px;
  overflow: hidden;
  color: var(--el-text-color-regular);
  font-family: Consolas, monospace;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-task-status {
  display: block;
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.muted-text {
  color: var(--el-text-color-placeholder);
}
</style>
