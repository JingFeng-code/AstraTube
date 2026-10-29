import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 前端固定 15273、後端固定 8420（見 backend 啟動指令）。
// 挑非常見的埠號是刻意的：8000／5173 太容易和機器上其他專案撞在一起。
// 想改用別的埠，前端設 PORT、前端呼叫後端的位址設 VITE_API_BASE。
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: Number(process.env.PORT) || 15273,
    strictPort: true,
  },
})
