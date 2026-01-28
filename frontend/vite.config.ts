import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  // Base path for production - matches FastAPI mount point
  base: '/ui/',

  plugins: [
    react(),
    tailwindcss(),
  ],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    proxy: {
      // Service endpoints (transcription API)
      '/service': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Speech-to-text endpoints
      '/speech-to-text': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Task management endpoints (plural - list)
      '/tasks': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Task detail endpoint (singular - by ID)
      '/task': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Health check endpoint
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // File upload endpoint
      '/upload': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // WebSocket endpoint for real-time progress
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
