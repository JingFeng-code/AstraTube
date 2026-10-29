import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Codespaces 需要監聽所有容器介面；本機仍只綁 loopback。
// 同源 /api 代理避免瀏覽器將 127.0.0.1 誤認為使用者自己的電腦。
export default defineConfig({
  plugins: [react()],
  server: {
    host: process.env.CODESPACES ? '0.0.0.0' : '127.0.0.1',
    port: Number(process.env.PORT) || 15273,
    strictPort: true,
    allowedHosts: ['.app.github.dev'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8420',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api(?=\/|$)/, ''),
      },
    },
  },
})
