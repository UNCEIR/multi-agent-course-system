import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'

// Next.js 16 + Vitest 官方推荐配置（参考 node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md）
// 用 .mts 后缀确保 vite-tsconfig-paths (ESM only) 能正确加载。
export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', '.next', 'out', 'build', 'dist'],
    css: false,
  },
})
