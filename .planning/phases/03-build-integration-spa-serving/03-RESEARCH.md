# Phase 3: Build Integration & SPA Serving - Research

**Researched:** 2026-01-27
**Domain:** Vite + React SPA serving from FastAPI at /ui route
**Confidence:** HIGH

## Summary

This phase integrates a React SPA built with Vite into the existing FastAPI backend, serving it at the `/ui` route with proper client-side routing support. The research confirms a well-established pattern: Vite builds the React app with a `base: '/ui/'` configuration, and FastAPI uses a catch-all route to serve `index.html` for all non-asset paths under `/ui`, enabling React Router to handle client-side navigation.

The development workflow uses Vite's proxy feature to forward API and WebSocket calls to the FastAPI backend, allowing independent hot-reload for both frontend and backend. Production deployment follows the user's decision: build locally, commit dist/ to repo, and deploy via `git pull` without server-side build steps.

The loading skeleton pattern uses inline CSS in `index.html` that displays while React/JS loads, providing immediate visual feedback. The noscript fallback provides a friendly "modern browser required" message styled with CSS.

**Primary recommendation:** Use Vite's `base: '/ui/'` configuration combined with FastAPI's catch-all route pattern for SPA serving. Use `concurrently` for single-command dev startup. Put skeleton CSS inline in index.html for instant display.

## Standard Stack

The established libraries/tools for this phase:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vite | 7.3.x | Build tool and dev server | Native ESM, <50ms HMR, first-party Tailwind plugin. Industry standard for React SPAs. |
| React | 19.2.x | UI framework | Per prior stack research. Latest stable with improved hooks. |
| React Router | 7.13.x | Client routing | Declarative mode for SPA navigation. No SSR needed. |
| Bun | 1.3.6 | Package manager | Per user decision. 2-3x faster installs than npm. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| concurrently | 9.x | Process runner | Run Vite and uvicorn together in dev |
| @types/node | latest | Node types | Required for vite.config.ts path resolution |

### FastAPI Integration
| Component | Purpose | Implementation |
|-----------|---------|----------------|
| StaticFiles | Serve built assets | Mount at `/ui/assets` |
| Catch-all route | SPA routing | `@app.get("/ui/{path:path}")` returns index.html |
| FileResponse | Serve HTML | Return index.html for non-asset paths |

**Installation:**
```bash
# From project root
bun create vite frontend --template react-ts
cd frontend
bun install
bun add -D concurrently @types/node
```

## Architecture Patterns

### Recommended Project Structure
```
whisperx/
├── app/                      # Existing FastAPI app
│   └── main.py               # Add SPA serving routes
├── frontend/                 # React SPA (NEW)
│   ├── src/
│   │   ├── components/
│   │   │   └── ui/           # shadcn components
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html            # Contains skeleton + noscript
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
├── package.json              # Root package.json for dev commands
└── pyproject.toml
```

### Pattern 1: Vite Base Path Configuration
**What:** Configure Vite to build assets with `/ui/` prefix so they load correctly when served from FastAPI's `/ui` mount point.
**When to use:** Always for embedded SPAs served from a subdirectory.
**Example:**
```typescript
// frontend/vite.config.ts
// Source: https://vite.dev/config/shared-options#base
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/ui/',  // Critical: all asset paths prefixed with /ui/
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/speech-to-text': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/tasks': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

### Pattern 2: FastAPI SPA Catch-All Route
**What:** Serve index.html for all paths under /ui that aren't static assets, enabling React Router to handle client-side navigation.
**When to use:** Always for SPAs with client-side routing.
**Example:**
```python
# app/main.py (additions)
# Source: https://gist.github.com/ultrafunkamsterdam/b1655b3f04893447c3802453e05ecb5e
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Path to built frontend
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

# Only mount if dist exists (production or after build)
if FRONTEND_DIST.exists():
    # Mount assets directory for JS, CSS, images
    app.mount("/ui/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="ui-assets")

    @app.get("/ui/{path:path}")
    async def serve_frontend(path: str):
        """Serve React SPA with client-side routing support."""
        file_path = FRONTEND_DIST / path
        # Serve file if it exists, otherwise serve index.html for SPA routing
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/ui")
    async def serve_frontend_root():
        """Serve React SPA at /ui (no trailing slash)."""
        return FileResponse(FRONTEND_DIST / "index.html")
```

### Pattern 3: Development Proxy and Concurrent Startup
**What:** Single command starts both Vite dev server and FastAPI backend.
**When to use:** Development workflow.
**Example:**
```json
// package.json in project root
{
  "scripts": {
    "dev": "concurrently \"bun run dev:api\" \"bun run dev:ui\"",
    "dev:api": "uvicorn app.main:app --reload --host localhost --port 8000",
    "dev:ui": "cd frontend && bunx --bun vite --port 5173",
    "build:ui": "cd frontend && bunx --bun vite build"
  },
  "devDependencies": {
    "concurrently": "^9.0.0"
  }
}
```

### Pattern 4: Loading Skeleton in index.html
**What:** Inline CSS skeleton displayed immediately while React/JS loads.
**When to use:** Improve perceived performance for SPA initial load.
**Example:**
```html
<!-- frontend/index.html -->
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>WhisperX</title>
    <style>
      /* Skeleton styles - displayed while React loads */
      .app-skeleton {
        max-width: 1200px;
        margin: 0 auto;
        padding: 24px;
      }
      .skeleton-header {
        height: 48px;
        background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
        border-radius: 8px;
        margin-bottom: 24px;
      }
      .skeleton-card {
        height: 200px;
        background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
        border-radius: 12px;
        margin-bottom: 16px;
      }
      .skeleton-row {
        display: flex;
        gap: 16px;
      }
      .skeleton-item {
        flex: 1;
        height: 120px;
        background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
        border-radius: 8px;
      }
      @keyframes shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
      }
      /* Hide skeleton when React loads */
      #root:not(:empty) + .app-skeleton { display: none; }
      /* Noscript fallback styling */
      .noscript-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        padding: 24px;
        font-family: system-ui, -apple-system, sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        text-align: center;
      }
      .noscript-icon { font-size: 64px; margin-bottom: 24px; }
      .noscript-title { font-size: 28px; font-weight: 600; margin-bottom: 16px; }
      .noscript-message { font-size: 18px; opacity: 0.9; max-width: 400px; line-height: 1.6; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <div class="app-skeleton">
      <div class="skeleton-header"></div>
      <div class="skeleton-card"></div>
      <div class="skeleton-row">
        <div class="skeleton-item"></div>
        <div class="skeleton-item"></div>
        <div class="skeleton-item"></div>
      </div>
    </div>
    <noscript>
      <div class="noscript-container">
        <div class="noscript-icon">&#128187;</div>
        <h1 class="noscript-title">Hey! This app needs a modern browser</h1>
        <p class="noscript-message">
          WhisperX requires JavaScript to work its magic.
          Please enable JavaScript or try a different browser to get started with transcription.
        </p>
      </div>
    </noscript>
    <script type="module" src="/ui/src/main.tsx"></script>
  </body>
</html>
```

### Anti-Patterns to Avoid
- **Mounting StaticFiles at /ui with html=True:** Does NOT support proper SPA routing; returns 404 for client-side routes on refresh
- **Using APIRouter for static files:** StaticFiles must be mounted on the main app, not a router
- **Hardcoding localhost:5173 in proxy:** Use relative paths in the app; proxy handles redirection
- **Building on server:** User decision is to build locally and commit dist/

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SPA routing fallback | Custom middleware to check routes | Catch-all route pattern | Edge cases with assets, query params, fragments |
| Dev proxy | Manual CORS configuration | Vite's server.proxy | Handles WebSocket upgrade, headers, connection management |
| Concurrent process running | Shell scripts with `&` | concurrently package | Cross-platform, colored output, proper termination |
| CSS shimmer animation | JavaScript animation | Pure CSS @keyframes | No JS needed, works before React loads |
| Path aliasing | Relative imports `../../` | Vite's resolve.alias + tsconfig paths | Cleaner imports, IDE support |

**Key insight:** The SPA serving pattern is deceptively complex. The catch-all route must come AFTER static file mounts, must handle both `/ui` and `/ui/`, must return proper MIME types for assets, and must not interfere with API routes. Use the established pattern.

## Common Pitfalls

### Pitfall 1: Assets Return 404 After Deployment
**What goes wrong:** Built JS/CSS files return 404 when accessed from browser.
**Why it happens:** Vite's `base` config doesn't match FastAPI's mount path, or assets directory not mounted correctly.
**How to avoid:**
- Set `base: '/ui/'` in vite.config.ts
- Mount assets at `/ui/assets` before the catch-all route
- Verify asset paths in built index.html start with `/ui/assets/`
**Warning signs:** Browser console shows 404 for .js and .css files.

### Pitfall 2: Client-Side Routes Return 404 on Refresh
**What goes wrong:** Navigating within app works, but refreshing the page returns FastAPI's 404.
**Why it happens:** FastAPI tries to match the URL path literally instead of returning index.html.
**How to avoid:**
- Catch-all route MUST return index.html for unknown paths
- Route must handle both with and without trailing slash
- Catch-all must be registered AFTER API routes and static mounts
**Warning signs:** Refresh on `/ui/transcripts` returns JSON 404 error.

### Pitfall 3: WebSocket Proxy Not Working in Dev
**What goes wrong:** WebSocket connections fail with HTTP 426 or connection refused.
**Why it happens:** Missing `ws: true` in proxy config, or wrong target protocol.
**How to avoid:**
- Use `ws: true` in proxy config
- Target must use `ws://` or `wss://` protocol
- Match the exact WebSocket path used by FastAPI
**Warning signs:** Browser console shows WebSocket connection failed, Network tab shows HTTP response instead of WS upgrade.

### Pitfall 4: Skeleton Visible After React Loads
**What goes wrong:** Skeleton flashes or remains visible after app renders.
**Why it happens:** CSS selector doesn't properly hide skeleton, or skeleton is inside #root.
**How to avoid:**
- Skeleton must be SIBLING of #root, not inside it
- Use CSS `:not(:empty)` selector to hide when React renders
- Alternatively, React component removes skeleton on mount
**Warning signs:** Two UIs visible briefly, or skeleton never disappears.

### Pitfall 5: Production Build Not Found
**What goes wrong:** FastAPI returns 404 for /ui in production.
**Why it happens:** dist/ folder doesn't exist or isn't at expected path.
**How to avoid:**
- Check `FRONTEND_DIST.exists()` before mounting
- Use absolute path from `__file__` for reliability
- Log warning if dist not found
**Warning signs:** No error message, just 404 for /ui.

## Code Examples

Verified patterns from official sources:

### Complete vite.config.ts
```typescript
// Source: https://vite.dev/config/
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],

  // Critical: matches FastAPI mount path
  base: '/ui/',

  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Generate source maps for debugging
    sourcemap: true,
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    port: 5173,
    // Proxy all API calls to FastAPI in development
    proxy: {
      // REST API endpoints
      '/speech-to-text': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/tasks': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/upload': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // WebSocket endpoint
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

### FastAPI SPA Handler Module
```python
# app/spa_handler.py
# Source: https://fastapi.tiangolo.com/tutorial/static-files/
"""SPA static file handler for React frontend."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

def setup_spa_routes(app: FastAPI, frontend_path: Path | None = None) -> None:
    """
    Configure FastAPI to serve the React SPA at /ui.

    Args:
        app: FastAPI application instance
        frontend_path: Path to built frontend dist folder.
                       Defaults to PROJECT_ROOT/frontend/dist
    """
    if frontend_path is None:
        frontend_path = Path(__file__).parent.parent / "frontend" / "dist"

    if not frontend_path.exists():
        logger.warning(
            f"Frontend dist folder not found at {frontend_path}. "
            "Run 'bun run build:ui' to build the frontend."
        )
        return

    index_html = frontend_path / "index.html"
    if not index_html.exists():
        logger.error(f"index.html not found in {frontend_path}")
        return

    assets_path = frontend_path / "assets"
    if assets_path.exists():
        # Mount assets first (before catch-all)
        app.mount(
            "/ui/assets",
            StaticFiles(directory=assets_path),
            name="ui-assets"
        )
        logger.info(f"Mounted UI assets from {assets_path}")

    @app.get("/ui")
    @app.get("/ui/")
    async def serve_ui_root() -> FileResponse:
        """Serve React SPA root."""
        return FileResponse(index_html)

    @app.get("/ui/{path:path}")
    async def serve_ui_path(path: str) -> FileResponse:
        """Serve React SPA with client-side routing support."""
        # Try to serve the exact file if it exists
        file_path = frontend_path / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Otherwise, serve index.html for client-side routing
        return FileResponse(index_html)

    logger.info(f"SPA routes configured at /ui from {frontend_path}")
```

### Root package.json for Dev Commands
```json
{
  "name": "whisperx-dev",
  "private": true,
  "scripts": {
    "dev": "concurrently -n api,ui -c blue,green \"bun run dev:api\" \"bun run dev:ui\"",
    "dev:api": "uvicorn app.main:app --reload --host localhost --port 8000",
    "dev:ui": "cd frontend && bunx --bun vite --port 5173",
    "build:ui": "cd frontend && bunx --bun vite build",
    "preview:ui": "cd frontend && bunx --bun vite preview"
  },
  "devDependencies": {
    "concurrently": "^9.1.0"
  }
}
```

### TypeScript Path Configuration
```json
// frontend/tsconfig.json
// Source: https://ui.shadcn.com/docs/installation/vite
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| StaticFiles with html=True | Catch-all route pattern | 2024 | html=True only serves directory index.html, not SPA routing |
| Create React App | Vite | 2023 | CRA deprecated, Vite is 10-20x faster |
| npm/yarn | Bun | 2024-2025 | 2-3x faster installs, native TypeScript |
| Tailwind v3 config | Tailwind v4 @tailwindcss/vite | 2025 | CSS-first config, automatic content detection |
| Manual CORS in dev | Vite proxy | 2020+ | Simpler, handles WS, no CORS headers needed |

**Deprecated/outdated:**
- **Create React App:** Unmaintained since 2023, use Vite
- **html=True on StaticFiles:** Does not handle SPA routing properly
- **PostCSS for Tailwind:** Tailwind v4 uses Vite plugin directly

## Open Questions

Things that couldn't be fully resolved:

1. **Dist folder location: frontend/dist vs app/static/ui**
   - What we know: Either works, user left to Claude's discretion
   - What's unclear: Project conventions, deployment preferences
   - Recommendation: Use `frontend/dist` to keep frontend concerns together; FastAPI references this path. Committed to repo per user decision.

2. **Trailing slash behavior**
   - What we know: Both `/ui` and `/ui/` should work
   - What's unclear: Whether to redirect one to the other
   - Recommendation: Handle both without redirect (simpler, fewer requests)

3. **Hot-reload coordination**
   - What we know: Vite HMR and uvicorn --reload work independently
   - What's unclear: Whether any coordination is needed
   - Recommendation: None needed; they're independent processes. Frontend changes use Vite HMR, backend changes restart uvicorn.

## Sources

### Primary (HIGH confidence)
- Vite config documentation - https://vite.dev/config/server-options (proxy configuration)
- Vite build options - https://vite.dev/config/build-options (outDir, base)
- FastAPI StaticFiles - https://fastapi.tiangolo.com/tutorial/static-files/
- Starlette StaticFiles - https://www.starlette.io/staticfiles/ (html parameter)
- shadcn/ui Vite setup - https://ui.shadcn.com/docs/installation/vite
- React Router SPA mode - https://reactrouter.com/how-to/spa
- Bun + Vite guide - https://bun.com/docs/guides/ecosystem/vite

### Secondary (MEDIUM confidence)
- FastAPI + React SPA gist - https://gist.github.com/ultrafunkamsterdam/b1655b3f04893447c3802453e05ecb5e (catch-all pattern)
- Skeleton loading patterns - https://blog.logrocket.com/build-skeleton-screen-css/
- Concurrently usage - https://dev.to/stamigos/modern-full-stack-setup-fastapi-reactjs-vite-mui-with-typescript-2mef

### Tertiary (LOW confidence)
- None - all patterns verified with official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Verified with official Vite, FastAPI, Bun documentation
- Architecture: HIGH - Pattern well-established, multiple official sources
- Pitfalls: HIGH - Documented in FastAPI discussions and community sources

**Research date:** 2026-01-27
**Valid until:** 60 days (stable patterns, unlikely to change)
