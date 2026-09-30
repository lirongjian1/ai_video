import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { tasksApi } from '@/api'
import type { AiTask } from '@/types'

export const useTaskStore = defineStore('tasks', () => {
  const items = ref<AiTask[]>([])
  const pendingCount = ref(0)
  const runningCount = ref(0)
  const loading = ref(false)
  const activeCount = computed(() => pendingCount.value + runningCount.value)

  async function refresh(silent = false) {
    if (!silent) loading.value = true
    try {
      const [recentResult, pendingResult, runningResult] = await Promise.all([
        tasksApi.list({ page_size: 20 }),
        tasksApi.list({ status: 'PENDING', page_size: 50 }),
        tasksApi.list({ status: 'RUNNING', page_size: 50 }),
      ])
      pendingCount.value = pendingResult.total
      runningCount.value = runningResult.total
      const merged = [...runningResult.items, ...pendingResult.items, ...recentResult.items]
      items.value = [...new Map(merged.map((item) => [item.id, item])).values()]
    } finally {
      if (!silent) loading.value = false
    }
  }

  async function cancel(taskId: number) {
    await tasksApi.cancel(taskId)
    await refresh(true)
  }

  async function remove(taskId: number) {
    await tasksApi.remove(taskId)
    await refresh(true)
  }

  return { items, activeCount, loading, refresh, cancel, remove }
})
