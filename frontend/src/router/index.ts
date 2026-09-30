import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'

import { supabase } from '@/lib/supabase'
import { pinia } from '@/stores'
import { useTabsStore } from '@/stores/tabs'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layout/AppLayout.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '工作台' } },
      { path: 'projects', name: 'projects', component: () => import('@/views/ProjectListView.vue'), meta: { title: '项目管理' } },
      { path: 'files', name: 'files', component: () => import('@/views/FileListView.vue'), meta: { title: '文件管理' } },
      { path: 'users', name: 'users', component: () => import('@/views/UserListView.vue'), meta: { title: '用户管理' } },
      { path: 'prompts', name: 'prompts', component: () => import('@/views/PromptListView.vue'), meta: { title: '提示词管理' } },
      { path: 'images', name: 'images', component: () => import('@/views/AssetLibraryView.vue'), props: { fileType: 'IMAGE' }, meta: { title: '图片管理' } },
      { path: 'characters', name: 'characters', component: () => import('@/views/CreativeEntityView.vue'), props: { entityType: 'characters' }, meta: { title: '角色管理' } },
      { path: 'scenes', name: 'scenes', component: () => import('@/views/CreativeEntityView.vue'), props: { entityType: 'scenes' }, meta: { title: '场景管理' } },
      { path: 'scripts', name: 'scripts', component: () => import('@/views/ScriptListView.vue'), meta: { title: '剧本管理' } },
      { path: 'video-tasks', redirect: '/' },
      { path: 'videos', name: 'videos', component: () => import('@/views/AssetLibraryView.vue'), props: { fileType: 'VIDEO' }, meta: { title: '视频管理' } },
      { path: 'video-merge', name: 'video-merge', component: () => import('@/views/VideoMergeView.vue'), meta: { title: '视频合成' } },
      { path: 'models', name: 'models', component: () => import('@/views/ModelConfigView.vue'), meta: { title: '模型管理' } },
      { path: 'secrets', name: 'secrets', component: () => import('@/views/SecretManageView.vue'), meta: { title: '密钥管理' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const { data } = await supabase.auth.getSession()
  const hasSession = Boolean(data.session)
  if (!to.meta.public && !hasSession) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && hasSession) return { name: 'dashboard' }
})

router.afterEach((to: RouteLocationNormalized) => {
  if (!to.meta.public) useTabsStore(pinia).open(to.fullPath, String(to.meta.title || '页面'))
})

export default router
