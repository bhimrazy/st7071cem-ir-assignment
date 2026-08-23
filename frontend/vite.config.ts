import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In dev, forward API calls to the FastAPI server so the frontend can use
    // same-origin relative URLs (/api/...) exactly as it does in production.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
