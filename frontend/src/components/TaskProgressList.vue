<script setup lang="ts">
import { CircleClose, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

import { errorMessage } from '@/api'
import { useTaskStore } from '@/stores/tasks'
import type { AiTask } from '@/types'

const props = withDefaults(defineProps<{ limit?: number }>(), { limit: 20 })
const taskStore = useTaskStore()
const { items, loading } = storeToRefs(taskStore)
const visibleItems = computed(() => items.value.slice(0, props.limit))
const typeLabels: Record<AiTask['task_type'], string> = { TEXT: '文本生成', IMAGE: '图片生成', VIDEO: '视频生成', MERGE: '视频合成' }
const statusLabels: Record<AiTask['status'], string> = { PENDING: '等待中', RUNNING: '执行中', SUCCESS: '成功', FAILED: '失败', CANCELLED: '已取消' }

function tagType(status: AiTask['status']) {
  return status === 'SUCCESS' ? 'success' : status === 'FAILED' ? 'danger' : status === 'RUNNING' ? 'warning' : 'info'
}

function progressStatus(status: AiTask['status']) {
  return status === 'SUCCESS' ? 'success' : status === 'FAILED' ? 'exception' : undefined
}

function providerStatus(task: AiTask) {
  return String(task.result_payload?.provider_status || '')
}

async function cancelTask(task: AiTask) {
  try {
    await ElMessageBox.confirm(`确定取消任务“${task.name}”吗？`, '取消任务', { type: 'warning' })
    await taskStore.cancel(task.id)
    ElMessage.success('任务已取消')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error, '取消任务失败'))
  }
}

async function removeTask(task: AiTask) {
  try {
    await ElMessageBox.confirm(`确定删除任务记录“${task.name}”吗？`, '删除任务', { type: 'warning' })
    await taskStore.remove(task.id)
    ElMessage.success('任务记录已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error, '删除任务失败'))
  }
}
</script>

<template>
  <div v-loading="loading" class="task-progress-list">
    <el-empty v-if="!loading && visibleItems.length === 0" description="暂无任务" :image-size="72" />
    <article v-for="task in visibleItems" :key="task.id" class="task-progress-row">
      <div class="task-main">
        <div class="task-title-row">
          <strong>{{ task.name }}</strong>
          <el-tag :type="tagType(task.status)" effect="plain" size="small">{{ statusLabels[task.status] }}</el-tag>
        </div>
        <div class="task-meta">
          <span>{{ typeLabels[task.task_type] }}</span>
          <span v-if="task.project_id">项目 #{{ task.project_id }}</span>
          <span>{{ new Date(task.created_at).toLocaleString() }}</span>
          <span v-if="providerStatus(task)">平台：{{ providerStatus(task) }}</span>
        </div>
        <el-progress :percentage="task.progress" :status="progressStatus(task.status)" :stroke-width="8" />
        <p v-if="task.error_message" class="task-error">{{ task.error_message }}</p>
      </div>
      <div class="task-actions">
        <el-button v-if="['PENDING', 'RUNNING'].includes(task.status)" text type="warning" :icon="CircleClose" @click="cancelTask(task)">取消</el-button>
        <el-button v-else text type="danger" :icon="Delete" @click="removeTask(task)">删除</el-button>
      </div>
    </article>
  </div>
</template>

<style scoped>
.task-progress-list { min-height: 112px; }
.task-progress-row { display: flex; gap: 16px; align-items: center; min-width: 0; padding: 14px 18px; border-bottom: 1px solid #e5e9e6; }
.task-progress-row:last-child { border-bottom: 0; }
.task-main { min-width: 0; flex: 1; }
.task-title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.task-title-row strong { overflow: hidden; color: #2d332f; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.task-meta { display: flex; flex-wrap: wrap; gap: 5px 14px; margin: 6px 0 9px; color: #7b837d; font-size: 12px; }
.task-error { margin: 7px 0 0; overflow: hidden; color: #ba4549; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.task-actions { flex: 0 0 auto; }
@media (max-width: 620px) {
  .task-progress-row { align-items: flex-start; padding: 13px 14px; }
  .task-actions :deep(.el-button) { width: 28px; padding: 0; overflow: hidden; }
}
</style>
