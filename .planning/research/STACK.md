# Stack Research

**Domain:** React frontend embedded in FastAPI (transcription workbench UI)
**Researched:** 2026-01-27
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| React | 19.2 | UI framework | Latest stable with improved hooks, Activity API, useEffectEvent. Industry standard for SPAs. | HIGH |
| Vite | 7.3.x | Build tooling | Native ESM, fast HMR (<50ms), first-party Tailwind plugin. Vite 7 requires Node 20.19+. | HIGH |
| Bun | 1.3.6 | Package manager + runtime | 2-3x faster installs than npm, native TypeScript, `bunx` for scripts. Replaces npm/node for dev. | HIGH |
| TypeScript | 5.7.x | Type safety | De facto standard for React projects. React 19 typings require TypeScript 5.0+. | HIGH |
| TailwindCSS | 4.1.x | Styling | CSS-first config, automatic content detection via Vite plugin. No PostCSS config needed. | HIGH |

### State Management

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| TanStack Query | 5.x | Server state | ALL API calls. Handles caching, deduplication, retries, optimistic updates. 80% of state needs. | HIGH |
| Zustand | 5.0.x | Client state | UI state (modals, sidebar), WebSocket connection state, file queue. Minimal API, 1KB bundle. | HIGH |

**Rationale:** TanStack Query replaces Redux/fetch boilerplate for server state. Zustand handles the remaining 20% of truly client-side state. This combo is the 2026 community default. Do NOT use Redux for new projects unless enterprise scale (5+ developers, strict patterns required).

### UI Components

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| shadcn/ui | latest | Component library | All UI components. Copy-paste into codebase, full ownership. Built on Radix + Tailwind. | HIGH |
| Radix UI | primitives | Accessibility layer | Comes with shadcn. Handles ARIA, keyboard nav, focus management. | HIGH |
| Lucide React | 0.474.x | Icons | All icons. Tree-shakeable, consistent style with shadcn. | MEDIUM |

**Rationale:** shadcn/ui is NOT a package dependency. Components are copied into your codebase (typically `src/components/ui/`). This gives full control and avoids breaking changes from library updates. The ecosystem has shifted decisively toward shadcn in 2025-2026.

### File Upload

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| react-dropzone | 14.3.x | Drag-and-drop | File upload zone. Handles drag events, file validation, multiple files. | HIGH |

**Rationale:** react-dropzone is a hook, not a UI component. Pair with shadcn-style dropzone component for styling. It does NOT handle HTTP uploads; use TanStack Query mutations for actual upload requests.

### Routing

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| React Router | 7.13.x | Client routing | SPA navigation. Declarative mode for simple routing (no SSR needed). | HIGH |

**Rationale:** React Router 7 merged Remix features but Declarative mode is sufficient for embedded SPAs. Do NOT use Framework mode; FastAPI handles server-side concerns.

### WebSocket Integration

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| Native WebSocket | - | Real-time updates | Progress streaming from FastAPI. Use with Zustand store for connection state. | HIGH |

**Rationale:** FastAPI has native WebSocket support via Starlette. No additional library needed. Create a custom hook that manages connection lifecycle and updates Zustand store.

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| Bun | 1.3.6 | Runtime + package manager | Use `bun install`, `bun run dev`, `bunx vite build` |
| Vitest | 3.x | Testing | Vite-native, faster than Jest. Use with @testing-library/react |
| ESLint | 9.x | Linting | Flat config format. Use @eslint/js + typescript-eslint |
| Prettier | 3.x | Formatting | With tailwindcss plugin for class sorting |

## Installation

```bash
# Initialize with Bun + Vite template
bun create vite webapp --template react-ts

# Install core dependencies
bun add react@19 react-dom@19 react-router@7 @tanstack/react-query zustand

# Install UI dependencies
bun add tailwindcss @tailwindcss/vite class-variance-authority clsx tailwind-merge
bun add @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-slot
bun add lucide-react react-dropzone

# Install dev dependencies
bun add -D typescript @types/react @types/react-dom
bun add -D vitest @testing-library/react @testing-library/jest-dom jsdom
bun add -D eslint @eslint/js typescript-eslint prettier prettier-plugin-tailwindcss
```

## Vite Configuration for FastAPI Embedding

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/ui/',  // Critical: matches FastAPI mount path
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',  // Proxy API calls in dev
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

## FastAPI Static File Integration

```python
# In app/main.py
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Mount built React app
WEBAPP_DIR = Path(__file__).parent.parent / "webapp" / "dist"

if WEBAPP_DIR.exists():
    app.mount("/ui/assets", StaticFiles(directory=WEBAPP_DIR / "assets"), name="ui-assets")

    @app.get("/ui/{path:path}")
    async def serve_ui(path: str):
        """Serve React SPA with client-side routing support."""
        file_path = WEBAPP_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(WEBAPP_DIR / "index.html")
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| React 19 | React 18 | If third-party libs have React 19 issues (rare as of Jan 2026) |
| Vite 7 | Vite 6 | Only if Node <20.19; Vite 6 supports Node 18 |
| shadcn/ui | MUI | Enterprise apps needing Material Design compliance |
| shadcn/ui | Ant Design | Data-heavy enterprise apps with CJK locale needs |
| Zustand | Jotai | Atomic state model preferred over flux-like |
| TanStack Query | SWR | Simpler API sufficient; SWR is smaller bundle |
| Bun | npm/node | CI environments without Bun support |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Create React App (CRA) | Deprecated, unmaintained since 2023. Slow builds. | Vite |
| Redux (without RTK) | Boilerplate-heavy, unnecessary for most apps | Zustand + TanStack Query |
| Redux Toolkit (RTK) | Overkill for single-team projects. RTK Query duplicates TanStack Query. | Zustand + TanStack Query |
| Axios | fetch is native, TanStack Query handles retries/caching | Native fetch + TanStack Query |
| Styled-components | Runtime CSS-in-JS hurts performance, ecosystem moved to Tailwind | TailwindCSS |
| Emotion | Same as styled-components; runtime overhead | TailwindCSS |
| Bootstrap | Dated look, CSS bloat, conflicts with Tailwind | shadcn/ui |
| socket.io-client | Unnecessary complexity; FastAPI uses native WebSocket | Native WebSocket |
| Webpack | Slower than Vite, more config needed | Vite |
| Jest | Slower than Vitest for Vite projects | Vitest |

## Stack Patterns by Variant

**For this transcription workbench UI:**
- Use shadcn's file upload block (react-dropzone based)
- Use TanStack Query for all API calls (`useQuery` for tasks, `useMutation` for uploads)
- Use native WebSocket with Zustand store for progress updates
- Use shadcn Table for transcript display with virtualization if >1000 segments

**If adding model management later:**
- Same stack applies
- Use TanStack Query's `useQueries` for parallel model status checks

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| React 19.2 | React Router 7.x | Router requires React 18+ |
| Vite 7.3 | Tailwind 4.1.x | Use @tailwindcss/vite plugin |
| Zustand 5.x | React 19 | Native useSyncExternalStore |
| TanStack Query 5 | React 19 | Full React 19 support |
| shadcn/ui | Radix primitives | shadcn uses Radix internally |
| Bun 1.3 | Vite 7 | Use `bunx --bun vite` for Bun runtime |

## Project Structure

```
webapp/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn components
│   │   ├── layout/          # App shell, sidebar, header
│   │   ├── upload/          # File upload components
│   │   ├── transcript/      # Transcript viewer components
│   │   └── models/          # Model management components
│   ├── hooks/
│   │   ├── use-websocket.ts # WebSocket connection hook
│   │   └── use-upload.ts    # File upload hook
│   ├── stores/
│   │   └── app-store.ts     # Zustand store
│   ├── api/
│   │   └── queries.ts       # TanStack Query definitions
│   ├── lib/
│   │   └── utils.ts         # cn() helper, etc.
│   ├── App.tsx
│   └── main.tsx
├── index.html
├── vite.config.ts
├── tailwind.config.ts       # Optional: only if customizing theme
├── tsconfig.json
└── package.json
```

## Sources

### HIGH Confidence (Official Documentation)

- Vite 7.3.1 release notes — https://vite.dev/releases (current stable version, Node 20.19+ requirement)
- TanStack Query v5 overview — https://tanstack.com/query/latest/docs/framework/react/overview
- Bun 1.3.6 release — https://github.com/oven-sh/bun/releases (latest stable, Jan 13 2026)
- React Router 7.13 changelog — https://reactrouter.com/changelog
- FastAPI Static Files — https://fastapi.tiangolo.com/tutorial/static-files/
- TailwindCSS v4 Vite plugin — https://tailwindcss.com/docs (@tailwindcss/vite 4.1.18)
- Zustand v5 migration — https://zustand.docs.pmnd.rs/migrations/migrating-to-v5

### MEDIUM Confidence (Multiple Credible Sources)

- shadcn/ui ecosystem adoption — https://www.untitledui.com/blog/react-component-libraries (2026 libraries comparison)
- React state management patterns — https://www.nucamp.co/blog/state-management-in-2026-redux-context-api-and-modern-patterns
- Zustand + TanStack Query combo — https://dev.to/martinrojas/federated-state-done-right-zustand-tanstack-query-and-the-patterns-that-actually-work-27c0
- FastAPI + React embedding — https://medium.com/@asafshakarzy/embedding-a-react-frontend-inside-a-fastapi-python-package-in-a-monorepo-c00f99e90471
- FastAPI WebSocket + React — https://medium.com/@suganthi2496/fastapi-websockets-react-real-time-features-for-your-modern-apps-b8042a10fd90

### LOW Confidence (Single Source / Training Data)

- react-dropzone version 14.3.x — npm registry (stable, but verify before install)

---
*Stack research for: React frontend embedded in FastAPI*
*Researched: 2026-01-27*
