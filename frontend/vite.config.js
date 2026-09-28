import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/app/' : '/',
  server: {
    proxy: {
      '/analyze': 'http://localhost:8000',
      '/analyses': 'http://localhost:8000',
    },
  },
}));