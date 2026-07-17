import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: '/veriagent/',
  plugins: [react()],
  server: {
    // Optional same-origin proxy when VITE_API_BASE_URL=/veriagent-api.
    // Default client.ts points at http://127.0.0.1:8000 directly (CORS allows Vite origins).
    proxy: {
      '/veriagent-api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/veriagent-api/, ''),
      },
    },
  },
})
