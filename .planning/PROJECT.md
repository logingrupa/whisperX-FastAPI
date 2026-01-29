# WhisperX Frontend UI

## What This Is

A production-ready web frontend for the WhisperX speech-to-text API. Users can upload audio/video files, transcribe them with speaker diarization, and export results in multiple formats. The UI is embedded in FastAPI and served at `/ui`.

## Core Value

Users can easily upload audio, transcribe with speaker identification, and export results — without touching the command line or API directly.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**Pre-existing Backend:**
- REST API for speech-to-text transcription — existing
- File upload endpoint (POST /speech-to-text) — existing
- URL-based transcription (POST /speech-to-text-url) — existing
- Task management (GET /tasks, GET /tasks/{id}) — existing
- Background processing with status tracking — existing
- Speaker diarization integration — existing
- Transcript alignment — existing
- Webhook callbacks on completion — existing
- Health check endpoints — existing

**v1.0 Frontend UI (shipped 2026-01-29):**
- React frontend served at /ui route — v1.0
- Drag-and-drop file upload with multi-file queue — v1.0
- Real-time transcription progress via WebSockets — v1.0
- Auto-detect language from filename (A03=Latvian, A04=Russian, A05=English) — v1.0
- Transcript viewer with speaker labels and timestamps — v1.0
- Export to SRT, VTT, TXT, and JSON formats — v1.0
- Language and model selection dropdowns — v1.0
- File format validation with magic byte verification — v1.0

### Active

<!-- Current scope. Building toward these. -->

- [ ] Model management: view loaded models, download new models
- [ ] Upload progress bar with speed and ETA
- [ ] Step timing display after completion
- [ ] State persistence on page refresh
- [ ] Responsive design improvements for tablet

### Out of Scope

- Mobile app — web-first, desktop/tablet focus
- User authentication — internal/trusted use for now
- Multi-tenancy — single user/team deployment
- Real-time streaming transcription — batch processing only
- Audio editing — transcription only, not an editor
- Inline transcript editing — complex state management, export to editor instead
- Video player with transcript sync — HTML5 video complexity

## Context

**Current State (v1.0 shipped):**
- 3,075 lines TypeScript/TSX frontend
- React + Vite + Tailwind v4 + shadcn/ui
- FastAPI backend with WebSocket progress system
- 7 phases, 21 plans completed in 3 days

**Tech Stack:**
- Backend: FastAPI, Python 3.11, SQLite, WhisperX
- Frontend: React 18, Vite, Bun, Tailwind v4
- Communication: WebSocket for progress, REST for CRUD

**Codebase Map:**
- See `.planning/codebase/` for detailed architecture analysis

## Constraints

- **Tech stack**: React + Vite (Bun), embedded in existing FastAPI
- **Deployment**: Single container, no separate frontend service
- **Browser support**: Modern browsers (Chrome, Firefox, Safari, Edge)
- **Language detection**: Must support A03/A04/A05 filename convention
- **Package manager**: Bun only for all commands (no npm/yarn/pnpm)
- **Code principles**: SRP (Single Responsibility Principle) and DRY (Don't Repeat Yourself)
- **UI components**: shadcn/ui + Radix only (no custom components)
- **Naming**: Full descriptive names only (no abbreviations like `btn`, `usr`, `msg`)

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Embed in FastAPI vs separate app | Simpler deployment, no CORS, single container | Good |
| React + Vite on Bun | User preference, modern tooling, fast builds | Good |
| WebSockets for progress | Better UX than polling for long transcriptions | Good |
| Filename-based language detection | User's existing workflow convention (A03/A04/A05) | Good |
| Tailwind v4 with CSS-first syntax | Modern approach, cleaner config | Good |
| Stage-based progress percentages | Transcription duration varies too much for time-based | Good |
| large-v3 as default model | User preference for accuracy over speed | Good |
| Discriminated union ApiResult<T> | Type-safe API results without exceptions | Good |
| Lazy load transcripts on expand | Avoids unnecessary API calls | Good |

---
*Last updated: 2026-01-29 after v1.0 milestone completion*
