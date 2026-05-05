import path from 'path'
import { defineConfig, loadEnv, type HttpProxy } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/

export default defineConfig(({ mode }) => {
  // Load env file based on mode (development, production)
  const env = loadEnv(mode, process.cwd(), '')

  // Backend API URL - defaults to localhost:8000
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000'
  const wsUrl = apiUrl.replace(/^http/, 'ws')

  // Backend route prefixes proxied to FastAPI in dev (DRY: single list).
  // Order matches FastAPI router prefixes — see app/main.py.
  const backendPrefixes = [
    '/service',         // transcription service endpoints
    '/speech-to-text',  // STT routes
    '/tasks',           // task list
    '/task',            // task detail by id
    '/health',          // health probe
    '/upload',          // direct POST upload
    '/uploads',         // tuspyserver chunked upload
    '/auth',             // Phase 13 auth: register/login/logout
    '/api',              // Phase 13: /api/keys, /api/account, /api/ws/ticket
    '/billing',          // Phase 13 billing
  ] as const

  // Forward dev origin to tuspyserver so Location response header points back
  // through the Vite proxy (same-origin) instead of leaking the backend host
  // (which would force the browser to cross-origin direct requests for PATCH).
  //
  // ProxyServer type is sourced from Vite's bundled `HttpProxy` namespace
  // (Vite re-exports its internal http-proxy-3 types) — avoids a phantom
  // dep on the unrelated `http-proxy` package and keeps `tsc -b` happy
  // under both bun (local) and npm (Forge) installs.
  const httpProxy = Object.fromEntries(
    backendPrefixes.map((prefix) => [
      prefix,
      {
        target: apiUrl,
        changeOrigin: true,
        configure: (proxy: HttpProxy.ProxyServer) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            const devHost = req.headers.host
            if (typeof devHost === 'string' && devHost.length > 0) {
              proxyReq.setHeader('X-Forwarded-Host', devHost)
              proxyReq.setHeader('X-Forwarded-Proto', 'http')
            }
          })
        },
      },
    ]),
  )

  return {
    // SPA mounts at site root in prod (Forge nginx serves dist/ at /).
    // Router has no basename — keep base/basename aligned end-to-end.
    base: '/',

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
        ...httpProxy,
        // WebSocket endpoint for real-time progress (separate target — ws://)
        '/ws': {
          target: wsUrl,
          ws: true,
          changeOrigin: true,
        },
      },
    },
  }
})
