import { defineConfig, loadEnv } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        '/api': apiProxyTarget,
        // 与 /api 一致转发到 FastAPI，避免浏览器请求 /health 落到 Vite 的 index.html
        '/health': apiProxyTarget,
      },
    },
  }
})
