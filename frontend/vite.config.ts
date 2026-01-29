import path from 'path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on mode (development, production)
  const env = loadEnv(mode, process.cwd(), '')

  // Backend API URL - defaults to localhost:8000
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000'
  const wsUrl = apiUrl.replace(/^http/, 'ws')

  return {
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
          target: apiUrl,
          changeOrigin: true,
        },
        // Speech-to-text endpoints
        '/speech-to-text': {
          target: apiUrl,
          changeOrigin: true,
        },
        // Task management endpoints (plural - list)
        '/tasks': {
          target: apiUrl,
          changeOrigin: true,
        },
        // Task detail endpoint (singular - by ID)
        '/task': {
          target: apiUrl,
          changeOrigin: true,
        },
        // Health check endpoint
        '/health': {
          target: apiUrl,
          changeOrigin: true,
        },
        // File upload endpoint
        '/upload': {
          target: apiUrl,
          changeOrigin: true,
        },
        // WebSocket endpoint for real-time progress
        '/ws': {
          target: wsUrl,
          ws: true,
          changeOrigin: true,
        },
      },
    },
  }
})
