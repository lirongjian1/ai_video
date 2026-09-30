<script setup lang="ts">
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api'
import { useAuthStore } from '@/stores/auth'

const form = reactive({ email: '', password: '' })
const loading = ref(false)
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

async function submit() {
  if (!form.email || !form.password) return ElMessage.warning('请输入邮箱和密码')
  loading.value = true
  try {
    await auth.login(form.email.trim(), form.password)
    await router.replace(String(route.query.redirect || '/'))
  } catch (error) {
    ElMessage.error(errorMessage(error, '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="identity-panel">
      <div class="identity-inner">
        <span class="product-code">AI VIDEO / WORKFLOW</span>
        <h1>把创意推进到完整视频</h1>
        <p>统一管理项目素材、生成任务与最终成片。</p>
        <div class="workflow-line" aria-hidden="true">
          <span>创意</span><i></i><span>分镜</span><i></i><span>视频</span><i></i><span>成片</span>
        </div>
      </div>
    </section>

    <section class="login-panel">
      <div class="login-form-wrap">
        <div class="mobile-brand">AI Video Workflow</div>
        <h2>登录工作台</h2>
        <p class="login-subtitle">使用系统账号继续</p>
        <el-form :model="form" size="large" @submit.prevent="submit">
          <el-form-item>
            <el-input v-model="form.email" placeholder="邮箱" autocomplete="username" :prefix-icon="User" />
          </el-form-item>
          <el-form-item>
            <el-input v-model="form.password" type="password" placeholder="密码" autocomplete="current-password" show-password :prefix-icon="Lock" @keyup.enter="submit" />
          </el-form-item>
          <el-button type="primary" native-type="button" :loading="loading" class="login-button" @click="submit">登录</el-button>
        </el-form>
        <p class="default-account">账号需先在 Supabase 后台创建，使用邮箱与密码登录</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page { display: grid; min-height: 100%; grid-template-columns: minmax(420px, 1.1fr) minmax(420px, .9fr); background: #fff; }
.identity-panel { display: flex; align-items: center; min-height: 100vh; padding: 64px; color: #f5f8f6; background: #202522; }
.identity-inner { width: min(620px, 100%); margin: auto; }
.product-code { color: #78b093; font-size: 12px; font-weight: 700; letter-spacing: 2px; }
.identity-inner h1 { max-width: 560px; margin: 22px 0 16px; font-size: clamp(38px, 5vw, 66px); line-height: 1.08; letter-spacing: 0; }
.identity-inner p { color: #bfc8c1; font-size: 17px; }
.workflow-line { display: flex; align-items: center; margin-top: 64px; color: #dce3de; font-size: 13px; }
.workflow-line i { width: clamp(24px, 5vw, 72px); height: 1px; margin: 0 12px; background: #58615b; }
.login-panel { display: grid; min-height: 100vh; padding: 48px; place-items: center; }
.login-form-wrap { width: min(390px, 100%); }
.mobile-brand { display: none; margin-bottom: 40px; color: #2f7d5c; font-weight: 800; }
h2 { margin: 0; color: #202522; font-size: 28px; letter-spacing: 0; }
.login-subtitle { margin: 8px 0 30px; color: #737b75; }
.login-button { width: 100%; margin-top: 4px; }
.default-account { margin-top: 22px; color: #858c87; font-size: 12px; text-align: center; }
@media (max-width: 840px) {
  .login-page { display: block; }
  .identity-panel { display: none; }
  .login-panel { padding: 28px; }
  .mobile-brand { display: block; }
}
</style>

