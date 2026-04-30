import path from 'path'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/

/**
 * Dev-only redirect for SPA routes typed without the /ui/ base prefix.
 *
 * Vite serves the app under `base: '/ui/'`. When a user types a bare path
 * like `/register` or `/login`, Vite's default 404 page suggests prepending
 * the base ("did you mean /ui/register?") which is helpful but two clicks
 * away. This plugin transparently 302-redirects bare app routes so direct
 * URLs always land on the right page in dev — production is handled by
 * FastAPI's SPA catch-all (app/spa_handler.py).
 *
 * Only matches GET requests for known client routes — never touches API
 * paths (which are listed in `proxy` and forwarded to FastAPI).
 */
function redirectBareSpaRoutes(routes: readonly string[]): Plugin {
  const matchSet = new Set(routes)
  return {
    name: 'whisperx-redirect-bare-spa-routes',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.method !== 'GET') return next()
        const url = req.url ?? '/'
        const [pathname] = url.split('?')
        if (!matchSet.has(pathname)) return next()
        const queryIndex = url.indexOf('?')
        const search = queryIndex >= 0 ? url.slice(queryIndex) : ''
        res.statusCode = 302
        res.setHeader('Location', `/ui${pathname}${search}`)
        res.end()
      })
    },
  }
}

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
    '/auth',            // Phase 13 auth: register/login/logout
    '/api',             // Phase 13: /api/keys, /api/account, /api/ws/ticket
    '/billing',         // Phase 13 billing
  ] as const

  // Forward dev origin to tuspyserver so Location response header points back
  // through the Vite proxy (same-origin) instead of leaking the backend host
  // (which would force the browser to cross-origin direct requests for PATCH).
  const httpProxy = Object.fromEntries(
    backendPrefixes.map((prefix) => [
      prefix,
      {
        target: apiUrl,
        changeOrigin: true,
        configure: (proxy: import('http-proxy').default) => {
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

  // SPA routes (React Router) that should redirect to `/ui/<path>` when
  // typed bare. Mirrors public routes in src/routes/AppRouter.tsx.
  const bareSpaRoutes = ['/register', '/login'] as const

  return {
    // Base path for production - matches FastAPI mount point
    base: '/ui/',

    plugins: [
      redirectBareSpaRoutes(bareSpaRoutes),
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
