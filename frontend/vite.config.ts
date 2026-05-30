import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: '/veriagent/',
  plugins: [react()],
  server: {
    // Same-origin proxy for local dev — avoids browser CORS against the remote API.
    proxy: {
      '/veriagent-api': {
        target: 'https://veriagent.dimikog.org',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/veriagent-api/, ''),
      },
    },
  },
})
