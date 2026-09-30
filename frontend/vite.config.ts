import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const projectRoot = fileURLToPath(new URL('../', import.meta.url))
  const env = loadEnv(mode, projectRoot, 'VITE_')
  const apiTarget = process.env.VITE_API_TARGET || env.VITE_API_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': apiTarget,
        '/storage': apiTarget,
      },
    },
  }
})

