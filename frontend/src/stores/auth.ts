import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { http, tokenStorageKey } from '@/api/http'
import type { User } from '@/types'

const USER_KEY = 'ai-video-user'

function readUser(): User | null {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(tokenStorageKey) || '')
  const user = ref<User | null>(readUser())
  const loggedIn = computed(() => Boolean(token.value))

  async function login(username: string, password: string) {
    const { data } = await http.post<{ access_token: string; user: User }>('/auth/login', {
      username,
      password,
    })
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem(tokenStorageKey, data.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
  }

  async function loadProfile() {
    if (!token.value) return
    const { data } = await http.get<User>('/auth/me')
    user.value = data
    localStorage.setItem(USER_KEY, JSON.stringify(data))
  }

  async function logout() {
    try {
      if (token.value) await http.post('/auth/logout')
    } finally {
      token.value = ''
      user.value = null
      localStorage.removeItem(tokenStorageKey)
      localStorage.removeItem(USER_KEY)
    }
  }

  return { token, user, loggedIn, login, loadProfile, logout }
})

