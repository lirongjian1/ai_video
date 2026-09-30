<script setup lang="ts">
import {
  Collection,
  DataAnalysis,
  Document,
  Files,
  Film,
  Fold,
  HomeFilled,
  Key,
  MagicStick,
  Menu as MenuIcon,
  Picture,
  Refresh,
  Setting,
  SwitchButton,
  Timer,
  User,
} from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import type { Component } from 'vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import TaskProgressList from '@/components/TaskProgressList.vue'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { useTaskStore } from '@/stores/tasks'

interface MenuEntry {
  path: string
  title: string
  icon: Component
  /** 仅管理员可见 */
  adminOnly?: boolean
}

const menuItems: MenuEntry[] = [
  { path: '/projects', title: '项目管理', icon: Collection },
  { path: '/files', title: '文件管理', icon: Files },
  { path: '/prompts', title: '提示词管理', icon: MagicStick },
  { path: '/images', title: '图片管理', icon: Picture },
  { path: '/characters', title: '角色管理', icon: User },
  { path: '/scenes', title: '场景管理', icon: DataAnalysis },
  { path: '/scripts', title: '剧本管理', icon: Document },
  { path: '/videos', title: '视频管理', icon: Film },
  { path: '/video-merge', title: '视频合成', icon: MenuIcon },
  { path: '/models', title: '模型管理', icon: Setting },
  { path: '/secrets', title: '密钥管理', icon: Key, adminOnly: true },
  { path: '/users', title: '用户管理', icon: User, adminOnly: true },
]

const collapsed = ref(false)
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const tabs = useTabsStore()
const taskStore = useTaskStore()
const { activeCount } = storeToRefs(taskStore)
const currentTitle = computed(() => String(route.meta.title || '工作台'))
const isAdmin = computed(() => auth.user?.role === 'ADMIN')
/** 普通用户不显示管理类菜单。 */
const visibleMenuItems = computed(() => menuItems.filter((item) => !item.adminOnly || isAdmin.value))
const taskDrawerVisible = ref(false)
let taskRefreshTimer: ReturnType<typeof setInterval> | undefined

async function closeTab(path: string) {
  const nextPath = tabs.close(path)
  if (route.fullPath === path) await router.push(nextPath)
}

function navigateTab(path: string | number) {
  router.push(String(path))
}

function removeTab(path: string | number) {
  closeTab(String(path))
}

async function logout() {
  await auth.logout()
  await router.replace('/login')
}

async function openTaskDrawer() {
  taskDrawerVisible.value = true
  await taskStore.refresh()
}

onMounted(() => {
  auth.loadProfile().catch(() => undefined)
  taskStore.refresh(true).catch(() => undefined)
  taskRefreshTimer = setInterval(() => taskStore.refresh(true).catch(() => undefined), 5000)
})

onUnmounted(() => clearInterval(taskRefreshTimer))
</script>

<template>
  <el-container class="app-shell">
    <el-aside :width="collapsed ? '72px' : '224px'" class="sidebar">
      <button class="brand" type="button" title="返回工作台" @click="router.push('/')">
        <span class="brand-mark">AV</span>
        <span v-if="!collapsed" class="brand-name">AI Video Workflow</span>
      </button>

      <el-menu
        :default-active="route.path"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        class="side-menu"
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <template #title>工作台</template>
        </el-menu-item>
        <el-menu-item v-for="item in visibleMenuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>

      <button class="collapse-button" type="button" :title="collapsed ? '展开菜单' : '收起菜单'" @click="collapsed = !collapsed">
        <el-icon><Fold :class="{ 'icon-reversed': collapsed }" /></el-icon>
      </button>
    </el-aside>

    <el-container class="main-shell">
      <el-header class="topbar">
        <div class="breadcrumb-title">{{ currentTitle }}</div>
        <div class="topbar-actions">
          <el-tooltip content="任务进度" placement="bottom">
            <el-badge :value="activeCount" :hidden="activeCount === 0" :max="99" class="task-badge">
              <el-button circle text aria-label="查看任务进度" @click="openTaskDrawer">
                <el-icon><Timer /></el-icon>
              </el-button>
            </el-badge>
          </el-tooltip>
          <el-tooltip content="刷新当前页" placement="bottom">
            <el-button circle text aria-label="刷新当前页" @click="tabs.refresh(route.fullPath)">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
          <el-dropdown trigger="click">
            <button class="user-button" type="button">
              <span class="avatar">{{ (auth.user?.nickname || auth.user?.username || 'A').slice(0, 1) }}</span>
              <span class="user-name">{{ auth.user?.nickname || auth.user?.username || 'admin' }}</span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :icon="SwitchButton" @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <div class="tabs-row">
        <el-tabs
          :model-value="route.fullPath"
          type="card"
          class="workspace-tabs"
          @tab-change="navigateTab"
          @tab-remove="removeTab"
        >
          <el-tab-pane
            v-for="tab in tabs.tabs"
            :key="tab.path"
            :name="tab.path"
            :label="tab.title"
            :closable="tab.closable"
          />
        </el-tabs>
        <el-dropdown trigger="click">
          <el-button class="tab-menu-button" text aria-label="Tab 操作">
            <el-icon><MenuIcon /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :icon="Refresh" @click="tabs.refresh(route.fullPath)">刷新当前页</el-dropdown-item>
              <el-dropdown-item @click="tabs.closeOthers(route.fullPath)">关闭其他页</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <el-main class="workspace">
        <router-view v-slot="{ Component: ViewComponent, route: viewRoute }">
          <keep-alive :max="16">
            <component
              :is="ViewComponent"
              :key="`${viewRoute.fullPath}:${tabs.refreshVersions[viewRoute.fullPath] || 0}`"
            />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>

    <el-drawer v-model="taskDrawerVisible" class="task-progress-drawer" title="任务进度" size="440px" append-to-body>
      <div class="drawer-toolbar">
        <span>执行中 {{ activeCount }} 个任务</span>
        <el-button text type="primary" :icon="Refresh" @click="taskStore.refresh()">刷新</el-button>
      </div>
      <TaskProgressList :limit="20" />
    </el-drawer>
  </el-container>
</template>

<style scoped>
.app-shell { height: 100%; background: #f3f5f3; }
.sidebar { position: relative; display: flex; flex-direction: column; overflow: hidden; color: #eef1ef; background: #202522; transition: width 160ms ease; }
.brand { display: flex; align-items: center; width: 100%; height: 62px; padding: 0 16px; color: inherit; background: transparent; border: 0; cursor: pointer; }
.brand-mark { display: grid; flex: 0 0 38px; width: 38px; height: 38px; place-items: center; color: #fff; background: #2f7d5c; border-radius: 6px; font-size: 13px; font-weight: 800; }
.brand-name { margin-left: 11px; overflow: hidden; font-size: 14px; font-weight: 700; white-space: nowrap; }
.side-menu { flex: 1; overflow-x: hidden; overflow-y: auto; border-right: 0; background: transparent; }
.side-menu:not(.el-menu--collapse) { width: 224px; }
.side-menu :deep(.el-menu-item) { height: 46px; color: #bfc7c1; }
.side-menu :deep(.el-menu-item:hover) { color: #fff; background: #2a302c; }
.side-menu :deep(.el-menu-item.is-active) { color: #fff; background: #2f7d5c; }
.collapse-button { display: grid; flex: 0 0 48px; width: 100%; place-items: center; color: #aab2ac; background: #1b1f1c; border: 0; cursor: pointer; }
.icon-reversed { transform: rotate(180deg); }
.main-shell { min-width: 0; }
.topbar { display: flex; align-items: center; justify-content: space-between; height: 62px; padding: 0 22px; background: #fff; border-bottom: 1px solid #dde2de; }
.breadcrumb-title { color: #303632; font-size: 16px; font-weight: 650; }
.topbar-actions, .user-button { display: flex; align-items: center; gap: 10px; }
.task-badge { display: inline-flex; }
.user-button { padding: 4px 6px; color: #313733; background: transparent; border: 0; cursor: pointer; }
.avatar { display: grid; width: 32px; height: 32px; place-items: center; color: #fff; background: #bf7025; border-radius: 50%; font-size: 13px; font-weight: 700; }
.user-name { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tabs-row { display: flex; height: 42px; padding: 0 8px 0 14px; background: #fff; border-bottom: 1px solid #dde2de; }
.workspace-tabs { min-width: 0; flex: 1; }
.workspace-tabs :deep(.el-tabs__header) { margin: 0; border-bottom: 0; }
.workspace-tabs :deep(.el-tabs__nav) { border: 0; }
.workspace-tabs :deep(.el-tabs__item) { height: 41px; border-left: 0; border-right: 0; border-top: 2px solid transparent; color: #6a716c; }
.workspace-tabs :deep(.el-tabs__item.is-active) { color: #2f7d5c; background: #f6faf8; border-top-color: #2f7d5c; }
.workspace-tabs :deep(.el-tabs__content) { display: none; }
.tab-menu-button { flex: 0 0 36px; margin: 3px 0; }
.workspace { min-width: 0; overflow: auto; padding: 22px; }
.drawer-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 0 18px 10px; color: #707872; font-size: 13px; border-bottom: 1px solid #e5e9e6; }
:global(.task-progress-drawer .el-drawer__body) { padding: 0; }
@media (max-width: 760px) {
  .sidebar { width: 72px !important; }
  .brand-name, .user-name { display: none; }
  .workspace { padding: 16px; }
  .topbar { padding: 0 14px; }
  :global(.task-progress-drawer) { width: 100% !important; }
}
</style>

