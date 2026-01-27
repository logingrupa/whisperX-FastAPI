# Architecture Research

**Domain:** React + FastAPI Integration for Transcription UI
**Researched:** 2026-01-27
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
                                    Single Container
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         FastAPI Application                           │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │  │
│  │  │   /api/*        │  │   /ws/*         │  │   /ui/*             │  │  │
│  │  │   REST API      │  │   WebSocket     │  │   Static Files      │  │  │
│  │  │   (existing)    │  │   (new)         │  │   (new)             │  │  │
│  │  └────────┬────────┘  └────────┬────────┘  └─────────┬───────────┘  │  │
│  │           │                    │                     │              │  │
│  │           ▼                    ▼                     ▼              │  │
│  │  ┌─────────────────────────────────────────────────────────────┐   │  │
│  │  │                    Services Layer                           │   │  │
│  │  │  TaskManagementService │ AudioProcessingService │ FileService │  │  │
│  │  └───────────────────────────────────────┬─────────────────────┘   │  │
│  │                                          │                          │  │
│  │  ┌───────────────────────────────────────┴─────────────────────┐   │  │
│  │  │                    Domain Layer                              │   │  │
│  │  │  Task Entity │ ITaskRepository │ ML Service Interfaces       │   │  │
│  │  └───────────────────────────────────────────────────────────────┘   │  │
│  │                                                                       │  │
│  │  ┌───────────────────────────────────────────────────────────────┐   │  │
│  │  │                  Infrastructure Layer                          │   │  │
│  │  │  SQLAlchemy Repository │ WhisperX ML Services │ WebSocket Hub  │   │  │
│  │  └───────────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         React SPA (Built)                             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │  │
│  │  │   Upload    │  │  Progress   │  │  Transcript │  │   Export   │  │  │
│  │  │   Page      │  │  Tracker    │  │  Viewer     │  │   Modal    │  │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘  │  │
│  │         │                │                │               │         │  │
│  │         ▼                ▼                ▼               ▼         │  │
│  │  ┌─────────────────────────────────────────────────────────────┐   │  │
│  │  │                    State Management                          │   │  │
│  │  │  Zustand Store (UI state) │ TanStack Query (server state)    │   │  │
│  │  └─────────────────────────────────────────────────────────────┘   │  │
│  │                                          │                          │  │
│  │  ┌───────────────────────────────────────┴─────────────────────┐   │  │
│  │  │                    API/Transport Layer                       │   │  │
│  │  │  fetch/axios (REST) │ WebSocket Client (progress)            │   │  │
│  │  └─────────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| FastAPI REST API | Handle CRUD operations, file uploads, task management | Existing `/speech-to-text`, `/tasks` endpoints |
| WebSocket Endpoint | Push progress updates to connected clients | New `/ws/tasks/{task_id}` endpoint with ConnectionManager |
| Static Files Server | Serve React build output (HTML, JS, CSS, assets) | SPAStaticFiles mounted at `/ui` |
| React Upload Page | File selection, drag-drop, language detection | Form component with axios/fetch upload |
| React Progress Tracker | Display real-time progress during transcription | WebSocket client + progress bar component |
| React Transcript Viewer | Display results with speaker labels, timestamps | Formatted transcript with export options |
| Zustand Store | Manage UI state (current task, modals, preferences) | Global store for cross-component state |
| TanStack Query | Cache and sync server state (task list, task details) | Queries with polling for task status |
| WebSocket Client | Maintain connection, handle reconnection, dispatch updates | Custom hook with reconnection logic |

## Recommended Project Structure

```
whisperx/
├── app/                              # Existing FastAPI backend
│   ├── api/
│   │   ├── audio_api.py              # Existing - add progress hooks
│   │   ├── task_api.py               # Existing
│   │   ├── websocket_api.py          # NEW: WebSocket endpoint
│   │   └── ui_api.py                 # NEW: SPA serving
│   ├── core/
│   │   └── websocket_manager.py      # NEW: Connection manager
│   ├── services/
│   │   └── audio_processing_service.py  # Modify: emit progress events
│   └── main.py                       # Modify: mount UI routes
│
├── ui/                               # NEW: React frontend source
│   ├── src/
│   │   ├── components/               # Reusable UI components
│   │   │   ├── FileUpload/
│   │   │   ├── ProgressBar/
│   │   │   ├── TranscriptViewer/
│   │   │   └── ExportModal/
│   │   ├── pages/                    # Route-level components
│   │   │   ├── UploadPage.tsx
│   │   │   ├── TasksPage.tsx
│   │   │   └── TranscriptPage.tsx
│   │   ├── hooks/                    # Custom React hooks
│   │   │   ├── useWebSocket.ts       # WebSocket connection hook
│   │   │   ├── useTaskProgress.ts    # Progress tracking hook
│   │   │   └── useLanguageDetect.ts  # Filename -> language
│   │   ├── stores/                   # Zustand stores
│   │   │   └── uiStore.ts            # UI state (modals, prefs)
│   │   ├── api/                      # API client functions
│   │   │   ├── tasks.ts              # Task CRUD operations
│   │   │   └── upload.ts             # File upload with progress
│   │   ├── lib/                      # Utilities
│   │   │   ├── websocket.ts          # WebSocket client class
│   │   │   └── export.ts             # SRT/VTT/JSON formatters
│   │   ├── App.tsx                   # Root component
│   │   └── main.tsx                  # Entry point
│   ├── public/                       # Static assets
│   ├── index.html                    # Vite entry
│   ├── vite.config.ts                # Vite config (base: /ui/)
│   └── package.json                  # Bun/npm dependencies
│
└── app/frontend/dist/                # Built output (gitignored)
    ├── index.html
    ├── assets/
    │   ├── index-[hash].js
    │   └── index-[hash].css
    └── ...
```

### Structure Rationale

- **`ui/` at root level**: Separates frontend source from Python code, clear boundary
- **`app/frontend/dist/`**: Build output inside app package for easy importing in FastAPI
- **`components/` with folders**: Each component gets folder for `.tsx`, `.css`, tests
- **`hooks/` for custom logic**: Reusable state logic separate from components
- **`stores/` for Zustand**: Centralized state definitions
- **`api/` for network calls**: All fetch/axios calls in one place for maintainability

## Architectural Patterns

### Pattern 1: SPA Static Files with Catch-All

**What:** Serve React build from FastAPI, with fallback to index.html for client-side routing
**When to use:** Embedded deployment, single container, avoiding CORS
**Trade-offs:** Simpler deployment vs. less flexible scaling

**Example:**
```python
# app/api/ui_api.py
from pathlib import Path
from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

class SPAStaticFiles(StaticFiles):
    """Static files handler that falls back to index.html for SPA routing."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code == 404:
                # Return index.html for client-side routing
                return await super().get_response("index.html", scope)
            raise ex

# In main.py - mount AFTER API routes
app.mount("/ui", SPAStaticFiles(directory="app/frontend/dist", html=True), name="ui")
```

### Pattern 2: WebSocket Connection Manager

**What:** Manage multiple WebSocket connections per task, enable broadcasting progress
**When to use:** Real-time progress updates to multiple clients watching same task
**Trade-offs:** In-memory state limits to single process; use Redis for multi-process

**Example:**
```python
# app/core/websocket_manager.py
from fastapi import WebSocket
from collections import defaultdict

class TaskProgressManager:
    """Manages WebSocket connections for task progress updates."""

    def __init__(self):
        # task_id -> list of connected websockets
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[task_id].append(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket):
        self.active_connections[task_id].remove(websocket)
        if not self.active_connections[task_id]:
            del self.active_connections[task_id]

    async def send_progress(self, task_id: str, progress: dict):
        """Broadcast progress to all clients watching this task."""
        for connection in self.active_connections.get(task_id, []):
            try:
                await connection.send_json(progress)
            except Exception:
                # Connection closed, will be cleaned up
                pass

# Singleton instance
progress_manager = TaskProgressManager()
```

### Pattern 3: Progress Emission from Background Tasks

**What:** Background processing emits progress events that WebSocket broadcasts
**When to use:** Long-running tasks (transcription) where users need feedback
**Trade-offs:** Adds complexity to processing logic; must handle missing connections

**Example:**
```python
# app/services/audio_processing_service.py
async def process_audio_task(
    task_id: str,
    file_path: str,
    progress_callback: Callable[[str, dict], Awaitable[None]] | None = None
):
    """Process audio with progress reporting."""

    async def emit_progress(stage: str, percent: int, message: str):
        if progress_callback:
            await progress_callback(task_id, {
                "stage": stage,
                "percent": percent,
                "message": message
            })

    await emit_progress("transcription", 0, "Starting transcription...")
    result = await transcription_service.transcribe(file_path)
    await emit_progress("transcription", 100, "Transcription complete")

    await emit_progress("alignment", 0, "Aligning words...")
    aligned = await alignment_service.align(result)
    await emit_progress("alignment", 100, "Alignment complete")

    # ... diarization, speaker assignment

    await emit_progress("complete", 100, "Processing complete")
    return final_result
```

### Pattern 4: Hybrid State Management (TanStack Query + Zustand)

**What:** TanStack Query for server state (tasks), Zustand for UI state (modals, preferences)
**When to use:** Apps with both server-synced data and local UI state
**Trade-offs:** Two libraries vs. one; clearer separation of concerns

**Example:**
```typescript
// hooks/useTasks.ts - Server state with TanStack Query
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchTasks, createTask, fetchTask } from '../api/tasks';

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 5000, // Poll for updates
  });
}

export function useTask(taskId: string) {
  return useQuery({
    queryKey: ['tasks', taskId],
    queryFn: () => fetchTask(taskId),
    refetchInterval: (data) =>
      data?.status === 'processing' ? 1000 : false, // Poll only while processing
  });
}

// stores/uiStore.ts - UI state with Zustand
import { create } from 'zustand';

interface UIState {
  selectedTaskId: string | null;
  exportModalOpen: boolean;
  setSelectedTask: (id: string | null) => void;
  openExportModal: () => void;
  closeExportModal: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedTaskId: null,
  exportModalOpen: false,
  setSelectedTask: (id) => set({ selectedTaskId: id }),
  openExportModal: () => set({ exportModalOpen: true }),
  closeExportModal: () => set({ exportModalOpen: false }),
}));
```

### Pattern 5: File Upload with Progress Tracking

**What:** Track upload progress separately from processing progress
**When to use:** Large file uploads where users need upload feedback
**Trade-offs:** Requires XMLHttpRequest or axios onUploadProgress; not native fetch

**Example:**
```typescript
// api/upload.ts
import axios from 'axios';

export interface UploadProgress {
  stage: 'uploading' | 'processing';
  percent: number;
}

export async function uploadFile(
  file: File,
  options: {
    language?: string;
    onProgress?: (progress: UploadProgress) => void;
  }
): Promise<{ task_id: string }> {
  const formData = new FormData();
  formData.append('file', file);
  if (options.language) {
    formData.append('language', options.language);
  }

  const response = await axios.post('/api/speech-to-text', formData, {
    onUploadProgress: (event) => {
      if (event.total) {
        options.onProgress?.({
          stage: 'uploading',
          percent: Math.round((event.loaded / event.total) * 100),
        });
      }
    },
  });

  return response.data;
}
```

## Data Flow

### Request Flow

```
[User selects file]
    │
    ▼
[FileUpload Component] ──────────────────────────────────────────┐
    │                                                            │
    │ POST /api/speech-to-text                                   │
    │ (multipart/form-data)                                      │
    │                                                            │
    ▼                                                            │
[FastAPI audio_api.py]                                           │
    │                                                            │
    │ validate file, create Task                                 │
    │                                                            │
    ▼                                                            │
[TaskManagementService] ───► [SQLAlchemy Repository] ───► [SQLite]
    │                                                            │
    │ schedule BackgroundTask                                    │
    │                                                            │
    ▼                                                            │
[Return task_id immediately] ────────────────────────────────────┤
                                                                 │
                              ┌───────────────────────────────────┘
                              │
[React receives task_id]      │ (async)
    │                         │
    ▼                         ▼
[Connect WebSocket]      [Background: process_audio_task()]
    │                         │
    │  ws://host/ws/tasks/id  │ transcribe → align → diarize
    │                         │
    ▼                         │
[WebSocket Endpoint] ◄────────┤ emit progress via manager
    │                         │
    │ send_json(progress)     │
    │                         │
    ▼                         ▼
[ProgressBar updates]    [Task marked complete]
                              │
                              │ update repository
                              ▼
                         [WebSocket sends final result]
                              │
                              ▼
                         [TranscriptViewer displays result]
```

### State Management

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         React Application                                │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    TanStack Query Cache                           │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │  │
│  │  │ ['tasks']      │  │ ['tasks', id]  │  │ ['models']         │  │  │
│  │  │ (all tasks)    │  │ (single task)  │  │ (loaded models)    │  │  │
│  │  └───────┬────────┘  └───────┬────────┘  └─────────┬──────────┘  │  │
│  └──────────┼───────────────────┼───────────────────────┼───────────┘  │
│             │                   │                       │              │
│             │ useQuery          │ useQuery              │ useQuery     │
│             ▼                   ▼                       ▼              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │
│  │  TasksPage       │  │  TranscriptPage  │  │  ModelsPage      │     │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘     │
│             │                   │                       │              │
│             │                   │                       │              │
│  ┌──────────┴───────────────────┴───────────────────────┴──────────┐  │
│  │                     Zustand UI Store                             │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │  │
│  │  │ selectedTask │  │ exportModal  │  │ uploadProgress       │   │  │
│  │  │ (string|null)│  │ (boolean)    │  │ { stage, percent }   │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    WebSocket Subscription                         │  │
│  │  task_id ──► useTaskProgress hook ──► progress state ──► UI      │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Data Flows

1. **File Upload Flow:** User drops file -> FormData POST -> FastAPI saves file -> Returns task_id -> React opens WebSocket -> Background processes -> WebSocket pushes progress -> UI updates

2. **Task List Flow:** TanStack Query polls `/api/tasks` every 5s -> Cache updated -> Components re-render with fresh data -> No manual state management needed

3. **Progress Update Flow:** Background task emits progress -> WebSocket manager broadcasts to subscribers -> React hook receives JSON -> Updates local state -> ProgressBar re-renders

4. **Export Flow:** User clicks export -> Zustand opens modal -> User selects format -> Format util transforms transcript -> Browser downloads file

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-100 users | Single container, in-memory WebSocket manager, SQLite, embedded React |
| 100-1k users | Consider PostgreSQL, keep single container, add health monitoring |
| 1k+ users | Split containers (API + workers), Redis for WebSocket pub/sub, S3 for files |

### Scaling Priorities

1. **First bottleneck:** ML processing (GPU-bound). Fix: Queue with dedicated workers, limit concurrent tasks
2. **Second bottleneck:** WebSocket connections (memory-bound). Fix: Redis pub/sub for multi-process, connection limits

## Anti-Patterns

### Anti-Pattern 1: Polling for Progress

**What people do:** Use setInterval or TanStack Query refetchInterval for progress updates
**Why it's wrong:** Creates unnecessary server load, delayed feedback, wastes resources
**Do this instead:** WebSockets for real-time progress, polling only for task list

### Anti-Pattern 2: Storing Progress in Database

**What people do:** Write every progress update to database, poll database for progress
**Why it's wrong:** Excessive writes, database becomes bottleneck, slower than WebSocket
**Do this instead:** In-memory progress via WebSocket, only persist final state

### Anti-Pattern 3: Separate CORS Configuration

**What people do:** Run React dev server on :3000, FastAPI on :8000, configure CORS
**Why it's wrong:** Production complexity, CORS security risks, two services to manage
**Do this instead:** Embed static build in FastAPI, same origin, no CORS needed (for this project's scale)

### Anti-Pattern 4: Redux for Simple UI State

**What people do:** Use Redux for everything including modal open/close state
**Why it's wrong:** Boilerplate overhead, unnecessary complexity for simple state
**Do this instead:** Zustand for UI state (simpler), TanStack Query for server state (built for it)

### Anti-Pattern 5: Blocking File Upload

**What people do:** Wait for entire file upload before returning response
**Why it's wrong:** Bad UX for large files, no progress feedback, timeout risks
**Do this instead:** Return task_id immediately, process in background, push progress via WebSocket

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| WhisperX ML | Python function calls via service interfaces | Already integrated via DDD pattern |
| SQLite/PostgreSQL | SQLAlchemy ORM via repository pattern | Already integrated |
| HuggingFace (diarization) | Pyannote via WhisperX | Requires HF_TOKEN env var |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| React <-> FastAPI REST | HTTP fetch/axios | Standard request-response |
| React <-> FastAPI WS | WebSocket JSON messages | Real-time, bidirectional |
| API <-> Services | Python function calls | Via dependency injection |
| Services <-> Infrastructure | Protocol interfaces | DDD pattern maintained |
| Background Task <-> WebSocket | In-memory manager | Same process; use Redis for multi-process |

## Build Order Implications

Based on component dependencies, recommended implementation order:

### Phase 1: Foundation (No React dependency)
1. **WebSocket endpoint** (`/ws/tasks/{task_id}`) - Can test with wscat/Postman
2. **ConnectionManager** - Manages connections, broadcasting
3. **Progress emission** - Modify audio_processing_service to emit progress

### Phase 2: Static Serving (Minimal React)
4. **SPAStaticFiles handler** - Serve any React build at /ui
5. **Vite configuration** - Configure base path, build output
6. **Basic React app** - Hello world served from FastAPI

### Phase 3: Core UI (React features)
7. **API client layer** - fetch/axios wrappers for /api endpoints
8. **TanStack Query setup** - Provider, hooks for tasks
9. **Task list page** - Display existing tasks

### Phase 4: Upload Flow
10. **File upload component** - Drag-drop, progress tracking
11. **Language detection hook** - Parse A03/A04/A05 from filename
12. **Upload page** - Complete upload flow

### Phase 5: Real-time Progress
13. **WebSocket client hook** - Connection, reconnection, messages
14. **Progress tracking** - Subscribe to task progress
15. **Progress UI** - Progress bar, stage indicators

### Phase 6: Results & Export
16. **Transcript viewer** - Display with speakers, timestamps
17. **Export utilities** - SRT, VTT, JSON formatters
18. **Export modal** - Format selection, download

### Dependency Chain
```
WebSocket Backend ─────────────────────────────────────────────────┐
        │                                                          │
        ▼                                                          │
Static Serving ─► React Setup ─► API Client ─► TanStack Query     │
                                     │                             │
                                     ▼                             │
                              Upload Component ─► Language Detect   │
                                     │                             │
                                     ▼                             │
                              WebSocket Hook ◄─────────────────────┘
                                     │
                                     ▼
                              Progress UI ─► Transcript Viewer ─► Export
```

## Sources

### Official Documentation
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) - HIGH confidence
- [FastAPI Static Files](https://fastapi.tiangolo.com/tutorial/static-files/) - HIGH confidence
- [TanStack Query Overview](https://tanstack.com/query/latest/docs/framework/react/overview) - HIGH confidence
- [Zustand GitHub](https://github.com/pmndrs/zustand) - HIGH confidence

### Integration Guides
- [FastAPI + WebSockets + React](https://medium.com/@suganthi2496/fastapi-websockets-react-real-time-features-for-your-modern-apps-b8042a10fd90) - MEDIUM confidence
- [Serving React with FastAPI](https://davidmuraya.com/blog/serving-a-react-frontend-application-with-fastapi/) - HIGH confidence (code examples verified)
- [FastAPI Full-Stack Template](https://github.com/fastapi/full-stack-fastapi-template) - HIGH confidence (official template)
- [FastAPI React Router Support](https://gist.github.com/ultrafunkamsterdam/b1655b3f04893447c3802453e05ecb5e) - MEDIUM confidence

### State Management
- [State Management in React 2026](https://www.c-sharpcorner.com/article/state-management-in-react-2026-best-practices-tools-real-world-patterns/) - MEDIUM confidence
- [TanStack Query Long Polling Discussion](https://github.com/TanStack/query/discussions/3540) - MEDIUM confidence

### File Upload
- [Uploading Files Using FastAPI](https://betterstack.com/community/guides/scaling-python/uploading-files-using-fastapi/) - HIGH confidence
- [React File Upload with Progress](https://dev.to/jbrocher/react-tips-tricks-uploading-a-file-with-a-progress-bar-3m5p) - MEDIUM confidence

---
*Architecture research for: React + FastAPI Integration*
*Researched: 2026-01-27*
