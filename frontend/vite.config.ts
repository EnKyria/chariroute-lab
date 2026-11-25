/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 本番は CloudFront 経由の同一オリジン（/api/* を API Gateway に振り分ける）を想定する。
// ローカル開発では Vite の proxy で /api を uvicorn（127.0.0.1:8000）に転送し、同じ相対パスで呼ぶ。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
})
