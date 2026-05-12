/* global process */
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_URL || 'http://127.0.0.1:57991'
  const wsTarget = apiTarget.replace(/^http/, 'ws')

  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        external: [/^@tauri-apps\//],
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': apiTarget,
        '/ws': { target: wsTarget, ws: true },
        '/health': apiTarget,
      },
    },
  }
})
