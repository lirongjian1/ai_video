import axios from 'axios'

const TOKEN_KEY = 'ai-video-token'

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('ai-video-user')
      window.location.assign('/login')
    }
    return Promise.reject(error)
  },
)

export const tokenStorageKey = TOKEN_KEY

export function errorMessage(error: unknown, fallback = '操作失败') {
  if (axios.isAxiosError(error)) return error.response?.data?.detail || error.message || fallback
  return fallback
}

