import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    proxy: {
      '/analyze': 'http://localhost:8000',
      '/analyses': 'http://localhost:8000',
    },
  },
})