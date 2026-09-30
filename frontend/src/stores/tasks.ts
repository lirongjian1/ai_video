import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { http } from '@/api/http'
import type { AiTask, PageResult } from '@/types'

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
        http.get<PageResult<AiTask>>('/tasks', { params: { page_size: 20 } }),
        http.get<PageResult<AiTask>>('/tasks', { params: { status: 'PENDING', page_size: 50 } }),
        http.get<PageResult<AiTask>>('/tasks', { params: { status: 'RUNNING', page_size: 50 } }),
      ])
      pendingCount.value = pendingResult.data.total
      runningCount.value = runningResult.data.total
      const merged = [...runningResult.data.items, ...pendingResult.data.items, ...recentResult.data.items]
      items.value = [...new Map(merged.map((item) => [item.id, item])).values()]
    } finally {
      if (!silent) loading.value = false
    }
  }

  async function cancel(taskId: number) {
    await http.post(`/tasks/${taskId}/cancel`)
    await refresh(true)
  }

  async function remove(taskId: number) {
    await http.delete(`/tasks/${taskId}`)
    await refresh(true)
  }

  return { items, activeCount, loading, refresh, cancel, remove }
})
