import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Local dev: Vite on :5173, API calls proxied to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
