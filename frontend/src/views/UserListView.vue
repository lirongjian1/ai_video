<script setup lang="ts">
import { Delete, Edit, Key, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onActivated, reactive, ref, watch } from 'vue'

import { errorMessage, usersApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref<string | null>(null)
const users = ref<User[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', status: '', page: 1, pageSize: 20 })
const form = reactive({ email: '', username: '', nickname: '', password: '', status: 'ENABLED' as User['status'], role: 'USER' as User['role'] })

const filteredUsers = computed(() => users.value.filter((user) => {
  const keyword = filters.keyword.trim().toLowerCase()
  if (keyword && !`${user.username} ${user.nickname} ${user.email}`.toLowerCase().includes(keyword)) return false
  if (filters.status && user.status !== filters.status) return false
  return true
}))
const pagedUsers = computed(() => filteredUsers.value.slice((filters.page - 1) * filters.pageSize, filters.page * filters.pageSize))

watch(() => [filters.keyword, filters.status, filters.pageSize], () => { filters.page = 1 })

async function loadUsers() {
  loading.value = true
  try {
    const result = await usersApi.list()
    users.value = result.items
    total.value = result.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '用户加载失败'))
  } finally {
    loading.value = false
  }
}

function search() {
  filters.page = 1
  loadUsers()
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { email: '', username: '', nickname: '', password: '', status: 'ENABLED', role: 'USER' })
  dialogVisible.value = true
}

function openEdit(user: User) {
  editingId.value = user.id
  Object.assign(form, { email: user.email, username: user.username, nickname: user.nickname, password: '', status: user.status, role: user.role })
  dialogVisible.value = true
}

async function saveUser() {
  if (!editingId.value && !form.email.trim()) return ElMessage.warning('请输入邮箱')
  if (!editingId.value && !form.username.trim()) return ElMessage.warning('请输入用户名')
  if (!editingId.value && form.password.length < 6) return ElMessage.warning('密码至少 6 位')
  saving.value = true
  try {
    if (editingId.value) {
      await usersApi.update({
        user_id: editingId.value,
        nickname: form.nickname,
        status: form.status,
        role: form.role,
        password: form.password || undefined,
      })
    } else {
      await usersApi.create({
        email: form.email.trim(),
        password: form.password,
        username: form.username.trim(),
        nickname: form.nickname,
        role: form.role,
      })
    }
    ElMessage.success(editingId.value ? '用户已更新' : '用户已创建')
    dialogVisible.value = false
    await loadUsers()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function toggleStatus(user: User, enabled: string | number | boolean) {
  const nextStatus = enabled ? 'ENABLED' : 'DISABLED'
  try {
    await usersApi.update({ user_id: user.id, status: nextStatus })
    user.status = nextStatus
    ElMessage.success(nextStatus === 'ENABLED' ? '用户已启用' : '用户已禁用')
  } catch (error) {
    ElMessage.error(errorMessage(error))
    await loadUsers()
  }
}

async function changePassword(user: User) {
  try {
    const result = await ElMessageBox.prompt(`为 ${user.username} 设置新密码`, '修改密码', {
      inputType: 'password',
      inputPattern: /^.{6,128}$/,
      inputErrorMessage: '密码长度应为 6 到 128 位',
      confirmButtonText: '保存',
    })
    await usersApi.update({ user_id: user.id, password: result.value })
    ElMessage.success('密码已修改')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error))
  }
}

async function removeUser(user: User) {
  try {
    await ElMessageBox.confirm(`确定删除用户“${user.username}”吗？`, '删除用户', { type: 'warning' })
    await usersApi.remove(user.id)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error))
  }
}

onActivated(loadUsers)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div><h1>用户管理</h1><p>维护系统账号及启用状态</p></div>
      <div class="page-actions"><el-button type="primary" :icon="Plus" @click="openCreate">新增用户</el-button></div>
    </div>

    <div class="filter-bar">
      <el-input v-model="filters.keyword" clearable placeholder="搜索用户名或昵称" style="width: 260px" :prefix-icon="Search" @keyup.enter="search" />
      <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 140px" @change="search"><el-option label="已启用" value="ENABLED" /><el-option label="已禁用" value="DISABLED" /></el-select>
      <el-button @click="search">查询</el-button>
    </div>

    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="pagedUsers" empty-text="暂无用户">
        <el-table-column prop="username" label="用户名" min-width="150" />
        <el-table-column prop="nickname" label="昵称" min-width="160"><template #default="{ row }"><span :class="{ muted: !row.nickname }">{{ row.nickname || '未设置' }}</span></template></el-table-column>
        <el-table-column label="状态" width="130">
          <template #default="{ row }"><el-switch :model-value="row.status === 'ENABLED'" :disabled="row.id === auth.user?.id" inline-prompt active-text="启用" inactive-text="禁用" @change="(value: string | number | boolean) => toggleStatus(row, value)" /></template>
        </el-table-column>
        <el-table-column label="最近登录" width="180"><template #default="{ row }"><span :class="{ muted: !row.last_login_time }">{{ row.last_login_time ? new Date(row.last_login_time).toLocaleString() : '尚未登录' }}</span></template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button text :icon="Key" @click="changePassword(row)">密码</el-button>
            <el-button v-if="row.id !== auth.user?.id" text type="danger" :icon="Delete" @click="removeUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="filteredUsers.length" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" /></div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑用户' : '新增用户'" width="min(500px, calc(100vw - 32px))">
      <el-form label-position="top">
        <el-form-item label="邮箱" :required="!editingId"><el-input v-model="form.email" :disabled="Boolean(editingId)" maxlength="150" /></el-form-item>
        <el-form-item label="用户名" :required="!editingId"><el-input v-model="form.username" :disabled="Boolean(editingId)" maxlength="64" /></el-form-item>
        <el-form-item label="昵称"><el-input v-model="form.nickname" maxlength="100" /></el-form-item>
        <el-form-item :label="editingId ? '新密码（不修改请留空）' : '初始密码'" :required="!editingId"><el-input v-model="form.password" type="password" show-password maxlength="128" /></el-form-item>
        <el-form-item label="角色"><el-segmented v-model="form.role" :options="[{ label: '普通用户', value: 'USER' }, { label: '管理员', value: 'ADMIN' }]" /></el-form-item>
        <el-form-item label="状态"><el-segmented v-model="form.status" :options="[{ label: '启用', value: 'ENABLED' }, { label: '禁用', value: 'DISABLED' }]" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveUser">保存</el-button></template>
    </el-dialog>
  </div>
</template>

