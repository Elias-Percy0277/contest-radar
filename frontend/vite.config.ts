import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// SPEC §7：开发代理 /api -> http://127.0.0.1:8300；生产构建产物 dist/ 由后端静态挂载
export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        // 大依赖单独分包，避免单 chunk 过大
        manualChunks: {
          echarts: ['echarts'],
          'element-plus': ['element-plus'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8300',
        changeOrigin: true,
      },
    },
  },
})
