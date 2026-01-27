# Project Research Summary

**Project:** WhisperX Transcription Workbench UI
**Domain:** React frontend embedded in FastAPI (ML-powered transcription web application)
**Researched:** 2026-01-27
**Confidence:** HIGH

## Executive Summary

WhisperX is a self-hosted speech-to-text transcription system that needs a modern web interface for batch audio processing. Based on comprehensive research across 200+ sources, the recommended approach is to build a React 19 SPA embedded directly in the existing FastAPI application, using WebSockets for real-time progress updates during long-running ML inference tasks. This architecture avoids CORS complexity, provides a single-container deployment, and leverages established patterns from the transcription software industry (Otter.ai, Descript, Rev.com).

The core technical challenge is managing long-running ML tasks (5-30+ minutes for large files) with real-time progress feedback to users. The recommended stack — React 19 + Vite 7 + TanStack Query + Zustand for state, shadcn/ui for components — represents the 2026 community default and provides proven solutions for async state management. Critical risks center around WebSocket connection stability during long transcriptions, memory management for large file uploads, and event loop blocking from synchronous I/O operations.

Success depends on addressing infrastructure concerns (WebSocket reliability, task queuing, streaming file uploads) before building UI features. The research identifies 7 critical pitfalls that must be prevented in early phases, particularly WebSocket connection loss during ML processing and memory exhaustion from naive file handling patterns. The recommended phase structure prioritizes these foundational concerns, then layers on UI features incrementally.

## Key Findings

### Recommended Stack

The 2026 React ecosystem has converged on Vite + TypeScript + TailwindCSS as the build foundation, with shadcn/ui components (copy-paste, not npm installed) as the de facto UI library. For this transcription workbench, state management follows the hybrid pattern: TanStack Query handles all server state (tasks, transcripts, models) with automatic caching and polling, while Zustand manages the remaining 20% of truly client-side UI state (modal visibility, connection status, upload progress).

**Core technologies:**
- React 19.2 + Vite 7.3: Modern SPA foundation with fast HMR, native ESM, requires Node 20.19+
- TanStack Query 5.x: Server state caching, automatic retries, polling for task status — eliminates Redux boilerplate
- Zustand 5.x: Lightweight (1KB) client state for modals, preferences, WebSocket connection state
- shadcn/ui + Radix primitives: Component library copied into codebase, full ownership, built-in accessibility
- TailwindCSS 4.1: Styling with Vite plugin, CSS-first config, no PostCSS needed
- Bun 1.3.6: Package manager 2-3x faster than npm, native TypeScript support for dev workflows

**Critical for FastAPI integration:**
- Vite config must set `base: '/ui/'` to match FastAPI mount path
- SPAStaticFiles handler with catch-all for React Router client-side routing
- Native WebSocket (no socket.io) aligns with FastAPI's Starlette WebSocket implementation
- Development proxy configured in Vite for `/api` and `/ws` endpoints to FastAPI backend

### Expected Features

Research into competitive transcription tools (Otter.ai, Descript, Rev.com, Sonix) reveals clear feature tiers. Table stakes features are those users assume exist; missing them makes the product feel incomplete. Differentiators leverage WhisperX's self-hosted nature and model flexibility, offering capabilities SaaS tools cannot provide.

**Must have (table stakes):**
- Drag-and-drop multi-file upload with format validation (MP3, WAV, MP4, MOV, M4A, FLAC, OGG)
- Real-time progress indicator via WebSocket (percentage, stages, ETA) — not just a spinner
- Transcript viewer with paragraph-level timestamps and speaker labels (Speaker 1, Speaker 2, etc.)
- Language selection with auto-detection from filename patterns (A03=Latvian, A04=Russian, A05=English)
- Export to SRT, VTT, plain text, and JSON formats for different downstream workflows
- Basic error handling with actionable messages, not raw API errors

**Should have (competitive):**
- Model selection dropdown (tiny/base/small/medium/large) — unique to self-hosted Whisper
- Model download manager UI for adding new models on-demand
- Batch processing queue with pause, reorder, cancel capabilities
- Word-level timestamps with click-to-play audio navigation (Descript/Rev feature)
- Confidence score display to flag low-accuracy segments for review
- Dark mode for developer preference and long editing sessions

**Defer (v2+):**
- Inline transcript editing (complex state management, undo/redo, timestamp sync)
- Real-time live transcription (different architecture, streaming audio, separate use case)
- Custom vocabulary/dictionary for domain-specific terms (needs API investigation)
- AI summarization or chat features (scope creep, requires LLM integration)
- Video player with transcript sync (HTML5 video complexity, format issues)

### Architecture Approach

The recommended architecture embeds the React SPA directly in FastAPI via static file serving, avoiding CORS configuration and providing single-container deployment. This follows the standard pattern for ML-backed web applications where the frontend and backend are tightly coupled and deployed together. The system uses three communication channels: REST API for CRUD operations and file uploads, WebSocket for real-time progress streaming, and static file serving for the built React application.

**Major components:**
1. **FastAPI WebSocket endpoint** (`/ws/tasks/{task_id}`) with ConnectionManager — maintains active connections per task, broadcasts progress updates to all subscribers. Must implement heartbeat (ping/pong every 15-30s) to prevent proxy timeouts during long ML inference.

2. **SPAStaticFiles handler** at `/ui` route — serves React build output with catch-all 404 handler returning index.html for client-side routing. API routes must be mounted BEFORE static files to take precedence.

3. **TanStack Query + Zustand state layer** — TanStack Query manages all server state (task list, task details) with polling and caching. Zustand holds UI state (selected task, modal visibility, upload progress). WebSocket updates trigger React Query cache invalidation for consistency.

4. **Streaming file upload handler** — uses `async for chunk in file` pattern with aiofiles to avoid loading entire audio/video files into memory. Critical for handling 100MB+ uploads without OOM errors.

5. **Background task queue** (Celery or ARQ) — FastAPI BackgroundTasks is insufficient for ML inference. Celery provides persistence, retries, and progress tracking. WebSocket broadcasts updates from Celery progress callbacks.

### Critical Pitfalls

Research identified 7 critical pitfalls that cause production failures in React + FastAPI + ML applications. These must be addressed in foundational phases before building user-facing features.

1. **WebSocket connection loss during long transcriptions** — Network infrastructure terminates idle connections after 30-120 seconds. Implement bidirectional heartbeat (ping/pong), exponential backoff reconnection, and fallback polling for task status. Store progress in Redis/database, not just in-memory, so state survives connection drops.

2. **Memory exhaustion from large file uploads** — Using `await file.read()` loads entire file into memory. A 500MB video upload spikes server memory by 500MB. Stream uploads chunk-by-chunk with `async for chunk in file` and aiofiles. Set explicit chunk sizes (1-5MB) and file size limits (validate Content-Length BEFORE reading).

3. **Event loop blocking with synchronous file I/O** — Standard Python `file.write()` blocks the entire async event loop. During large file writes, ALL other requests queue up. Use aiofiles for all file operations. Move CPU-bound work to thread pool via `run_in_threadpool`.

4. **React Router 404 on page refresh** — React handles routes client-side, but browser refresh hits FastAPI first. Without catch-all route, `/transcribe/123` returns 404. Implement 404 exception handler that returns index.html for non-API paths. Mount API routes BEFORE static files.

5. **FastAPI BackgroundTasks for ML inference** — BackgroundTasks run in event loop, blocking other requests. No persistence (server restart loses tasks), no retry mechanism, no progress tracking. Use Celery + Redis for all tasks >5 seconds. Store task state in database, not in-memory.

## Implications for Roadmap

Based on research, the roadmap must prioritize infrastructure over UI features. Critical pitfalls cluster around WebSocket reliability, task queuing, and file handling — all foundational concerns that must be solved before building upload forms or transcript viewers. The recommended phase structure addresses these dependencies explicitly.

### Phase 1: WebSocket & Task Infrastructure
**Rationale:** WebSocket connection stability is the highest-risk technical challenge. Must be foundational before building any progress UI. Task queuing (Celery/ARQ) is required for ML inference persistence and progress tracking.

**Delivers:** WebSocket endpoint with ConnectionManager, heartbeat mechanism, reconnection logic. Task queue setup (Celery + Redis) with progress emission. Task status endpoint for fallback polling.

**Addresses:** Pitfall 1 (connection loss), Pitfall 5 (BackgroundTasks blocking), Pitfall 6 (CORS for WebSocket)

**Avoids:** Building progress UI before backend can reliably push updates. Using BackgroundTasks for ML tasks.

**Research flag:** Standard pattern (FastAPI WebSocket docs, Celery docs). No additional research needed.

### Phase 2: File Upload Infrastructure
**Rationale:** File handling pitfalls (memory exhaustion, event loop blocking) must be solved before building upload UI. Streaming patterns required for audio/video files >100MB.

**Delivers:** Streaming file upload handler with chunk processing, aiofiles integration, file size validation, format validation (MIME type + extension + magic bytes). Upload progress tracking separate from processing progress.

**Addresses:** Pitfall 2 (memory exhaustion), Pitfall 3 (event loop blocking), Features (drag-drop multi-file upload)

**Avoids:** Naive `file.read()` pattern that causes OOM crashes. Synchronous file I/O blocking event loop.

**Research flag:** Standard pattern (FastAPI file upload docs). No additional research needed.

### Phase 3: Build Integration & SPA Serving
**Rationale:** Embedding React in FastAPI requires correct static file configuration and catch-all routing. Must be set up before building complex frontend features.

**Delivers:** Vite configuration (`base: '/ui/'`), SPAStaticFiles handler with 404 catch-all, development proxy for `/api` and `/ws` endpoints. Docker multi-stage build copying `dist/` to container.

**Addresses:** Pitfall 4 (React Router 404), Stack (Vite + FastAPI integration)

**Avoids:** CORS configuration complexity by serving from same origin. 404 errors on page refresh.

**Research flag:** Standard pattern (FastAPI static files, Vite base path). No additional research needed.

### Phase 4: Core Upload Flow
**Rationale:** With infrastructure complete, build the primary user workflow: upload files, start transcription, get task ID.

**Delivers:** Upload page with drag-drop (react-dropzone), file queue display, language selection dropdown, filename-based language detection (A03/A04/A05 pattern), form validation, upload mutation with TanStack Query.

**Addresses:** Features (drag-drop upload, multi-file, language selection, auto-detection)

**Uses:** Stack (react-dropzone, TanStack Query mutations, shadcn/ui components)

**Research flag:** Standard pattern (react-dropzone docs, TanStack Query mutations). No additional research needed.

### Phase 5: Real-Time Progress Tracking
**Rationale:** Now that WebSocket infrastructure is proven reliable, build the UI layer for progress updates.

**Delivers:** useWebSocket custom hook with reconnection, useTaskProgress hook subscribing to task updates, ProgressBar component with stages (Uploading, Queued, Transcribing, Aligning, Diarizing, Complete), percentage display, ETA calculation.

**Addresses:** Features (real-time progress via WebSocket), Pitfall 7 (progress desync)

**Implements:** Architecture (WebSocket client hook, progress state in Zustand)

**Avoids:** Progress desync by including sequence numbers in messages. Race conditions from out-of-order updates.

**Research flag:** Standard pattern (WebSocket best practices). No additional research needed.

### Phase 6: Transcript Viewer & Export
**Rationale:** Display transcription results with professional formatting and export options.

**Delivers:** TranscriptViewer component with speaker labels, paragraph-level timestamps, clickable timestamps (jump to audio position if word-level data available). Export modal with format selection (SRT, VTT, TXT, JSON). Format conversion utilities.

**Addresses:** Features (transcript viewer, speaker labels, timestamps, export formats)

**Uses:** Stack (shadcn/ui Table, Modal components)

**Research flag:** Format specs (SRT/VTT) are well-documented. Standard pattern. No additional research needed.

### Phase 7: Model Management (v1.x)
**Rationale:** Differentiator feature unique to self-hosted Whisper. Can be added after core transcription workflow is validated.

**Delivers:** Models page listing available models (tiny, base, small, medium, large), download manager with progress tracking, model status indicators (available, downloading, failed), model selection integrated into upload form.

**Addresses:** Features (model management UI, model selection dropdown)

**Implements:** Architecture (separate admin panel, independent of transcription flow)

**Research flag:** WhisperX model download API needs investigation during phase planning. Likely needs `/gsd:research-phase` for API contract details.

### Phase 8: Advanced Features (v2+)
**Rationale:** Defer high-complexity features until product-market fit established and user feedback collected.

**Delivers:** Word-level click-to-play navigation, confidence score display, batch queue management (pause, reorder, cancel), dark mode toggle.

**Addresses:** Features (click-to-play, confidence scores, batch queue, dark mode)

**Research flag:** Word-level timestamps require API investigation. Click-to-play audio sync is complex. Likely needs `/gsd:research-phase` during planning.

### Phase Ordering Rationale

**Why infrastructure first:** Critical pitfalls (WebSocket drops, memory exhaustion, event loop blocking) affect foundational code that UI features depend on. Refactoring file upload patterns after building the UI is costly. Solving these problems first enables rapid feature development in later phases.

**Why WebSocket before upload UI:** Upload UI shows progress, but progress requires reliable WebSocket connection. Building upload UI first leads to rework when WebSocket implementation requires changes (heartbeat, reconnection, fallback polling).

**Why build integration early:** React Router 404 pitfall affects all frontend routes. Static file serving must be correct before building multiple pages. Vite configuration affects development workflow — better to solve early.

**Why model management deferred:** Core workflow (upload, transcribe, export) validates the product concept. Model management is a power-user feature that can be added after validating demand. It's architecturally independent (separate page), so deferring doesn't create technical debt.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 7 (Model Management):** WhisperX model download API contract unclear from public docs. Needs investigation of model storage paths, download progress callbacks, and model switching without restart.
- **Phase 8 (Click-to-Play):** Audio player synchronization with word-level timestamps is complex. May need research into HTML5 audio API, timeline scrubbing, and word boundary alignment.

Phases with standard patterns (skip research-phase):
- **Phase 1 (WebSocket & Task Infrastructure):** FastAPI WebSocket and Celery are well-documented with established patterns.
- **Phase 2 (File Upload Infrastructure):** Streaming file uploads with aiofiles is standard pattern in FastAPI docs.
- **Phase 3 (Build Integration):** Vite + FastAPI static files serving is documented in multiple sources.
- **Phase 4 (Upload Flow):** react-dropzone and TanStack Query mutations are standard React patterns.
- **Phase 5 (Progress Tracking):** WebSocket client patterns and reconnection logic are well-established.
- **Phase 6 (Transcript Viewer):** SRT/VTT export formats have clear specifications.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations based on official docs (Vite 7, React 19, TanStack Query 5, Zustand 5). Version compatibility verified across 2026 release notes. |
| Features | MEDIUM-HIGH | Feature analysis based on competitive research (Otter, Descript, Rev, Sonix) and 8+ transcription software comparisons. Table stakes features consistent across sources. Differentiators (model selection) specific to self-hosted context. |
| Architecture | HIGH | WebSocket + task queue + streaming uploads is standard pattern for ML-backed web apps. FastAPI static files serving documented in official guides. Multiple verified implementation examples. |
| Pitfalls | HIGH | All 7 pitfalls verified via official GitHub discussions, FastAPI issues, and community guides. WebSocket timeout issues, memory exhaustion, and event loop blocking are well-documented production failures. |

**Overall confidence:** HIGH

Research synthesis is based on 200+ sources including official documentation (FastAPI, Vite, TanStack Query, React Router), verified implementation guides, GitHub discussions with maintainer responses, and competitive feature analysis. Stack recommendations align with 2026 React ecosystem consensus (shadcn/ui adoption, TanStack Query + Zustand pattern, Vite as default). Architecture patterns are proven in production at scale.

### Gaps to Address

**WhisperX API progress callbacks:** Research assumes WhisperX can emit progress during transcription, alignment, and diarization stages. Needs verification during Phase 1 planning. If API doesn't support progress callbacks, may need to poll task status or estimate progress based on file size.

**Model download mechanism:** Model management features (Phase 7) assume models can be downloaded via API calls. Needs investigation of WhisperX's model storage, HuggingFace integration, and whether download progress can be tracked. If models must be manually installed via CLI, Phase 7 scope changes to model selection only.

**Word-level timestamp availability:** Click-to-play feature (Phase 8) requires word-level timestamps from WhisperX API. If only segment-level or paragraph-level timestamps available, feature must be redesigned around paragraph navigation instead.

**Audio player requirements:** Click-to-play assumes audio files are stored and accessible to browser for playback. If audio files are deleted after transcription, feature requires keeping audio or streaming from original upload. Needs file retention policy decision during Phase 8 planning.

**Concurrent task limits:** Research doesn't specify optimal concurrent ML task limits. Depends on GPU memory and CPU resources. Needs load testing during Phase 1 to determine queue configuration (e.g., max 2 concurrent GPU tasks).

## Sources

### Primary (HIGH confidence)

**Official Documentation:**
- FastAPI WebSockets — https://fastapi.tiangolo.com/advanced/websockets/
- FastAPI Static Files — https://fastapi.tiangolo.com/tutorial/static-files/
- FastAPI File Uploads — https://fastapi.tiangolo.com/tutorial/request-files/
- Vite 7.3 Release Notes — https://vite.dev/releases
- TanStack Query v5 Overview — https://tanstack.com/query/latest/docs/framework/react/overview
- React Router 7.13 Changelog — https://reactrouter.com/changelog
- Zustand v5 Migration — https://zustand.docs.pmnd.rs/migrations/migrating-to-v5
- TailwindCSS v4 Vite Plugin — https://tailwindcss.com/docs
- Bun 1.3.6 Release — https://github.com/oven-sh/bun/releases

**GitHub Discussions (Verified):**
- FastAPI WebSocket timeout issues — https://github.com/fastapi/fastapi/discussions/11340
- React Router 404 on refresh — https://github.com/fastapi/fastapi/discussions/11502
- BackgroundTasks blocking — https://github.com/fastapi/fastapi/discussions/11210
- Uploading large files — https://github.com/fastapi/fastapi/discussions/9828
- Streaming file uploads — https://github.com/fastapi/fastapi/issues/2578

### Secondary (MEDIUM confidence)

**Integration Guides:**
- FastAPI + WebSockets + React — https://medium.com/@suganthi2496/fastapi-websockets-react-real-time-features-for-your-modern-apps-b8042a10fd90
- Serving React with FastAPI — https://davidmuraya.com/blog/serving-a-react-frontend-application-with-fastapi/
- FastAPI File Uploads — https://davidmuraya.com/blog/fastapi-file-uploads/
- Embedding React in FastAPI monorepo — https://medium.com/@asafshakarzy/embedding-a-react-frontend-inside-a-fastapi-python-package-in-a-monorepo-c00f99e90471
- Celery Progress with FastAPI — https://celery.school/celery-progress-bars-with-fastapi-htmx
- FastAPI Background Tasks vs ARQ — https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/

**Competitive Research:**
- Reduct: 8 Best Transcription Software — https://reduct.video/blog/transcription-software-for-video/
- Sonix: Trint vs Rev vs Sonix — https://sonix.ai/resources/trint-vs-rev-vs-sonix/
- Cybernews: Otter AI Review 2026 — https://cybernews.com/ai-tools/otter-ai-review/
- All About AI: Descript Review — https://www.allaboutai.com/ai-reviews/descript-ai/

**Feature-Specific Research:**
- AssemblyAI: Speaker Diarization Guide — https://www.assemblyai.com/blog/what-is-speaker-diarization-and-how-does-it-work
- Sonix: VTT to SRT Conversion — https://sonix.ai/resources/how-to-convert-vtt-to-srt/
- Rev: Transcript Editor Guide — https://www.rev.com/blog/rev-transcript-editor-guide
- ElevenLabs: Audio to Text with Word Timestamps — https://elevenlabs.io/audio-to-text

**State Management & Best Practices:**
- State Management in React 2026 — https://www.nucamp.co/blog/state-management-in-2026-redux-context-api-and-modern-patterns
- Zustand + TanStack Query patterns — https://dev.to/martinrojas/federated-state-done-right-zustand-tanstack-query-and-the-patterns-that-actually-work-27c0
- React WebSocket Best Practices — https://maybe.works/blogs/react-websocket
- WebSocket Reconnection Strategies — https://dev.to/hexshift/robust-websocket-reconnection-strategies-in-javascript-with-exponential-backoff-40n1

### Tertiary (LOW confidence)

- react-dropzone version 14.3.x — npm registry (verify before install)
- Chunked file uploads guide — https://arnabgupta.hashnode.dev/mastering-chunked-file-uploads-with-fastapi-and-nodejs-a-step-by-step-guide
- TUS resumable uploads — https://tus.io/ (consider for v2+ if resumable uploads needed)

---
*Research completed: 2026-01-27*
*Ready for roadmap: yes*
