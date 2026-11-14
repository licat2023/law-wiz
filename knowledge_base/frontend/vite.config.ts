/** 构建知识库管理界面，并为开发服务器配置独立的知识库 API 代理。 */
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue()],
    server: {
      port: 5174,
      proxy: {
        '/api': { target: env.KB_API_TARGET || 'http://127.0.0.1:8100', changeOrigin: true },
      },
    },
    build: { rollupOptions: { output: { manualChunks: { element: ['element-plus'] } } } },
  }
})
