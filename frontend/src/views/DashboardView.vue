<script setup lang="ts">
import { Collection, Files, Plus, RefreshRight, Timer, User } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import { onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { http } from '@/api/http'
import TaskProgressList from '@/components/TaskProgressList.vue'
import { useTaskStore } from '@/stores/tasks'
import type { AiFile, PageResult, Project, User as UserType } from '@/types'

const router = useRouter()
const taskStore = useTaskStore()
const { activeCount, loading: taskLoading } = storeToRefs(taskStore)
const loading = ref(false)
const counts = ref({ projects: 0, files: 0, users: 0 })
const recentProjects = ref<Project[]>([])
const taskSection = ref<HTMLElement | null>(null)

async function loadData() {
  loading.value = true
  try {
    const [projects, files, users] = await Promise.all([
      http.get<PageResult<Project>>('/projects', { params: { page_size: 5 } }),
      http.get<PageResult<AiFile>>('/files', { params: { page_size: 1 } }),
      http.get<PageResult<UserType>>('/users', { params: { page_size: 1 } }),
      taskStore.refresh(true),
    ])
    counts.value = {
      projects: projects.data.total,
      files: files.data.total,
      users: users.data.total,
    }
    recentProjects.value = projects.data.items
  } finally {
    loading.value = false
  }
}

function showTasks() {
  taskSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(loadData)
onActivated(loadData)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div>
        <h1>工作台</h1>
        <p>项目、素材与生成任务的实时概览</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Plus" type="primary" @click="router.push('/projects')">新建项目</el-button>
      </div>
    </div>

    <section class="metric-grid">
      <button class="metric" type="button" @click="router.push('/projects')">
        <span class="metric-icon green"><el-icon><Collection /></el-icon></span>
        <span><strong>{{ counts.projects }}</strong><small>项目</small></span>
      </button>
      <button class="metric" type="button" @click="router.push('/files')">
        <span class="metric-icon amber"><el-icon><Files /></el-icon></span>
        <span><strong>{{ counts.files }}</strong><small>素材文件</small></span>
      </button>
      <button class="metric" type="button" @click="showTasks">
        <span class="metric-icon red"><el-icon><Timer /></el-icon></span>
        <span><strong>{{ activeCount }}</strong><small>执行中任务</small></span>
      </button>
      <button class="metric" type="button" @click="router.push('/users')">
        <span class="metric-icon charcoal"><el-icon><User /></el-icon></span>
        <span><strong>{{ counts.users }}</strong><small>系统用户</small></span>
      </button>
    </section>

    <section ref="taskSection" class="content-panel task-panel">
      <div class="section-heading">
        <div><h2>任务进度</h2><p>生成任务会自动更新，可在这里取消或清理记录</p></div>
        <el-button text type="primary" :icon="RefreshRight" :loading="taskLoading" @click="taskStore.refresh()">刷新</el-button>
      </div>
      <TaskProgressList :limit="10" />
    </section>

    <section class="content-panel recent-panel">
      <div class="section-heading">
        <div><h2>最近项目</h2><p>按最近更新时间排序</p></div>
        <el-button text type="primary" @click="router.push('/projects')">查看全部</el-button>
      </div>
      <el-table :data="recentProjects" empty-text="暂无项目">
        <el-table-column prop="name" label="项目名称" min-width="220" />
        <el-table-column prop="description" label="描述" min-width="280" show-overflow-tooltip />
        <el-table-column label="状态" width="120">
          <template #default="{ row }"><el-tag effect="plain" type="success">{{ row.status === 'ACTIVE' ? '进行中' : row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ new Date(row.updated_at).toLocaleString() }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(170px, 1fr)); gap: 14px; margin-bottom: 18px; }
.metric { display: flex; align-items: center; gap: 14px; min-height: 102px; padding: 18px; text-align: left; background: #fff; border: 1px solid #dde2de; border-radius: 6px; cursor: pointer; transition: transform 140ms ease, box-shadow 140ms ease; }
.metric:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgb(30 45 36 / 8%); }
.metric-icon { display: grid; width: 44px; height: 44px; place-items: center; border-radius: 6px; font-size: 21px; }
.metric-icon.green { color: #2f7d5c; background: #e6f1ec; }
.metric-icon.amber { color: #a95e1e; background: #f7ebdf; }
.metric-icon.red { color: #aa3f42; background: #f7e6e6; }
.metric-icon.charcoal { color: #404742; background: #e9ecea; }
.metric strong, .metric small { display: block; }
.metric strong { color: #202522; font-size: 25px; line-height: 30px; }
.metric small { margin-top: 2px; color: #737b75; font-size: 12px; }
.task-panel { margin-bottom: 18px; overflow: hidden; scroll-margin-top: 16px; }
.recent-panel { overflow: hidden; }
.section-heading { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px; border-bottom: 1px solid #dde2de; }
.section-heading h2 { margin: 0; font-size: 16px; letter-spacing: 0; }
.section-heading p { margin: 3px 0 0; color: #818882; font-size: 12px; }
@media (max-width: 1050px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .metric-grid { grid-template-columns: 1fr; } }
</style>

