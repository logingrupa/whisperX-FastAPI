# Roadmap: WhisperX Frontend UI

## Overview

This roadmap delivers a production-ready web frontend for the WhisperX speech-to-text API. The approach follows research recommendations: infrastructure-first (WebSocket reliability, streaming uploads, SPA serving) before building user-facing features (upload UI, progress tracking, transcript viewer). Each phase delivers a coherent, verifiable capability that subsequent phases depend on.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: WebSocket & Task Infrastructure** - Backend foundation for real-time progress updates
- [x] **Phase 2: File Upload Infrastructure** - Streaming upload patterns for large audio/video files
- [x] **Phase 3: Build Integration & SPA Serving** - React embedded in FastAPI at /ui route
- [x] **Phase 4: Core Upload Flow** - Drag-drop upload with language/model selection
- [ ] **Phase 5: Real-Time Progress Tracking** - WebSocket-powered progress UI with stage display
- [ ] **Phase 6: Transcript Viewer & Export** - View results and download in multiple formats

## Phase Details

### Phase 1: WebSocket & Task Infrastructure
**Goal**: Backend can push real-time progress updates to connected clients reliably
**Depends on**: Nothing (first phase)
**Requirements**: None (infrastructure, enables PROG-01, PROG-02, PROG-03)
**Success Criteria** (what must be TRUE):
  1. WebSocket endpoint accepts connections and maintains them during long operations
  2. Heartbeat mechanism prevents proxy timeouts during 5-30 minute transcriptions
  3. Task progress can be retrieved via fallback polling endpoint if WebSocket fails
  4. Progress updates include percentage, current stage, and error information
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md - WebSocket endpoint with ConnectionManager and heartbeat
- [x] 01-02-PLAN.md - Task progress emission and fallback polling endpoint

### Phase 2: File Upload Infrastructure
**Goal**: Backend handles large audio/video uploads (up to 5GB) without memory exhaustion or event loop blocking
**Depends on**: Phase 1
**Requirements**: UPLD-04 (format validation)
**Success Criteria** (what must be TRUE):
  1. User can upload 500MB+ files without server memory spikes
  2. System validates file format before processing begins (rejects unsupported formats with clear message)
  3. Other requests remain responsive during large file uploads
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md - Streaming upload with streaming-form-data and direct-to-disk writing
- [x] 02-02-PLAN.md - Magic byte validation using puremagic for spoofing protection

### Phase 3: Build Integration & SPA Serving
**Goal**: React SPA builds and serves correctly from FastAPI at /ui route
**Depends on**: Phase 1
**Requirements**: None (infrastructure, enables all UI requirements)
**Success Criteria** (what must be TRUE):
  1. User can access React application at /ui in browser
  2. User can refresh any page without 404 error (client-side routing works)
  3. Development mode proxies API and WebSocket calls to FastAPI backend
  4. Production build serves static files from FastAPI container
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md - React frontend with Vite, TypeScript, Tailwind, skeleton loading
- [x] 03-02-PLAN.md - FastAPI SPA handler and root dev commands
- [x] 03-03-PLAN.md - Integration verification checkpoint

### Phase 4: Core Upload Flow
**Goal**: Users can upload audio/video files with language and model selection
**Depends on**: Phase 2, Phase 3
**Requirements**: UPLD-01, UPLD-02, UPLD-03, UPLD-05, LANG-01, LANG-02
**Success Criteria** (what must be TRUE):
  1. User can drag-and-drop audio/video files onto upload zone
  2. User can select files via file picker dialog
  3. User can upload multiple files and see queue display
  4. System auto-detects language from filename pattern (A03=Latvian, A04=Russian, A05=English)
  5. User can select transcription language from dropdown (overriding auto-detection)
  6. User can select Whisper model size (tiny/base/small/medium/large)
**Plans**: 4 plans

Plans:
- [x] 04-01-PLAN.md - Initialize shadcn/ui and react-dropzone
- [x] 04-02-PLAN.md - Create upload types and language detection
- [x] 04-03-PLAN.md - File queue hook and dropzone component
- [x] 04-04-PLAN.md - Queue display, selects, and page assembly

### Phase 5: Real-Time Progress Tracking
**Goal**: Users see live transcription progress with stage indicators and error handling
**Depends on**: Phase 4
**Requirements**: PROG-01, PROG-02, PROG-03
**Success Criteria** (what must be TRUE):
  1. User sees real-time progress percentage via WebSocket
  2. User sees which stage is active (Uploading, Queued, Transcribing, Aligning, Diarizing, Complete)
  3. User sees clear error message when processing fails (not raw API errors)
  4. Progress updates resume after brief connection loss (reconnection with backoff)
**Plans**: 3 plans

Plans:
- [ ] 05-01-PLAN.md — Setup: Install react-use-websocket, add Progress component, create types and stage config
- [ ] 05-02-PLAN.md — Hooks: Create useTaskProgress hook with WebSocket, extend useFileQueue with progress tracking
- [ ] 05-03-PLAN.md — UI: Create StageBadge, FileProgress, ConnectionStatus components and integrate into FileQueueItem

### Phase 6: Transcript Viewer & Export
**Goal**: Users can view transcription results and download in multiple formats
**Depends on**: Phase 5
**Requirements**: VIEW-01, VIEW-02, DOWN-01, DOWN-02, DOWN-03, DOWN-04
**Success Criteria** (what must be TRUE):
  1. User can view transcript with paragraph-level timestamps
  2. User can see speaker labels (Speaker 1, Speaker 2, etc.)
  3. User can download transcript as SRT file
  4. User can download transcript as VTT file
  5. User can download transcript as plain text file
  6. User can download transcript as JSON with full metadata
**Plans**: TBD

Plans:
- [ ] 06-01: Transcript viewer component with timestamps and speaker labels
- [ ] 06-02: Export modal with format selection
- [ ] 06-03: Format conversion utilities (SRT, VTT, TXT, JSON)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. WebSocket & Task Infrastructure | 2/2 | Complete | 2026-01-27 |
| 2. File Upload Infrastructure | 2/2 | Complete | 2026-01-27 |
| 3. Build Integration & SPA Serving | 3/3 | Complete | 2026-01-27 |
| 4. Core Upload Flow | 4/4 | Complete | 2026-01-27 |
| 5. Real-Time Progress Tracking | 0/3 | Not started | - |
| 6. Transcript Viewer & Export | 0/3 | Not started | - |

---
*Roadmap created: 2026-01-27*
*Milestone: v1.0 Frontend UI*
