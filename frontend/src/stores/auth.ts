import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { supabase } from '@/lib/supabase'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const ready = ref(false)
  const loggedIn = computed(() => Boolean(user.value))

  /** 从 profiles 拉取档案，组装成前端 User。 */
  async function loadProfile() {
    const { data: auth } = await supabase.auth.getUser()
    if (!auth.user) {
      user.value = null
      return null
    }
    const { data: profile } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', auth.user.id)
      .single()
    user.value = {
      id: auth.user.id,
      email: auth.user.email ?? '',
      username: profile?.username ?? auth.user.email ?? '',
      nickname: profile?.nickname ?? '',
      role: (profile?.role ?? 'USER') as User['role'],
      status: (profile?.status ?? 'ENABLED') as User['status'],
      last_login_time: profile?.last_login_time ?? null,
      created_at: profile?.created_at ?? new Date().toISOString(),
      updated_at: profile?.updated_at ?? new Date().toISOString(),
    }
    return user.value
  }

  async function login(email: string, password: string) {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw new Error(translateAuthError(error.message))
    const profile = await loadProfile()
    if (profile) {
      await supabase
        .from('profiles')
        .update({ last_login_time: new Date().toISOString() })
        .eq('id', profile.id)
    }
    return profile
  }

  async function logout() {
    await supabase.auth.signOut()
    user.value = null
  }

  /** 初始化：恢复会话并监听登录状态变化。 */
  async function init() {
    await loadProfile()
    ready.value = true
    supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        user.value = null
      } else {
        void loadProfile()
      }
    })
  }

  return { user, ready, loggedIn, login, logout, loadProfile, init }
})

function translateAuthError(message: string): string {
  const map: Record<string, string> = {
    'Invalid login credentials': '邮箱或密码错误',
    'Email not confirmed': '邮箱尚未确认，请联系管理员',
    'User already registered': '该邮箱已注册',
    'Password should be at least 6 characters': '密码至少 6 位',
  }
  return map[message] ?? message
}
