import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface WorkspaceTab {
  path: string
  title: string
  closable: boolean
}

const HOME_TAB: WorkspaceTab = { path: '/', title: '工作台', closable: false }
const STORAGE_KEY = 'ai-video-workspace-tabs'

function restoreTabs(): WorkspaceTab[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]') as WorkspaceTab[]
    return [HOME_TAB, ...saved.filter((item) => !['/', '/video-tasks'].includes(item.path))]
  } catch {
    return [HOME_TAB]
  }
}

export const useTabsStore = defineStore('tabs', () => {
  const tabs = ref<WorkspaceTab[]>(restoreTabs())
  const refreshVersions = ref<Record<string, number>>({})

  function persist() {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tabs.value))
  }

  function open(path: string, title: string) {
    if (!tabs.value.some((item) => item.path === path)) {
      tabs.value.push({ path, title, closable: path !== '/' })
      persist()
    }
  }

  function close(path: string) {
    const index = tabs.value.findIndex((item) => item.path === path)
    if (index <= 0) return '/'
    tabs.value.splice(index, 1)
    persist()
    return tabs.value[Math.max(0, index - 1)]?.path || '/'
  }

  function refresh(path: string) {
    refreshVersions.value[path] = (refreshVersions.value[path] || 0) + 1
  }

  function closeOthers(path: string) {
    tabs.value = tabs.value.filter((item) => !item.closable || item.path === path)
    persist()
  }

  return { tabs, refreshVersions, open, close, refresh, closeOthers }
})

