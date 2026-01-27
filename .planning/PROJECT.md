# WhisperX Frontend UI

## What This Is

A production-ready web frontend for the WhisperX speech-to-text API. Users can upload audio/video files, transcribe them with speaker diarization, manage Whisper models, and export results in multiple formats. The UI is embedded in FastAPI and served at `/ui`.

## Core Value

Users can easily upload audio, transcribe with speaker identification, and export results — without touching the command line or API directly.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ REST API for speech-to-text transcription — existing
- ✓ File upload endpoint (POST /speech-to-text) — existing
- ✓ URL-based transcription (POST /speech-to-text-url) — existing
- ✓ Task management (GET /tasks, GET /tasks/{id}) — existing
- ✓ Background processing with status tracking — existing
- ✓ Speaker diarization integration — existing
- ✓ Transcript alignment — existing
- ✓ Webhook callbacks on completion — existing
- ✓ Health check endpoints — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] React frontend served at /ui route
- [ ] File upload with drag-and-drop support
- [ ] Real-time transcription progress via WebSockets
- [ ] Auto-detect language from filename (A03=Latvian, A04=Russian, A05=English)
- [ ] Model management: view loaded models, download new models, switch between models
- [ ] Transcript viewer with speaker labels and timestamps
- [ ] Export to SRT, VTT, and JSON formats
- [ ] Responsive design for desktop and tablet

### Out of Scope

- Mobile app — web-first, desktop/tablet focus
- User authentication — internal/trusted use for now
- Multi-tenancy — single user/team deployment
- Real-time streaming transcription — batch processing only
- Audio editing — transcription only, not an editor

## Context

**Existing Backend:**
- FastAPI application with DDD architecture
- WhisperX for transcription, alignment, diarization
- SQLite database for task persistence
- Background task processing
- Python 3.11, UV package manager

**Frontend Addition:**
- React + Vite built with Bun
- Static files served from FastAPI at /ui
- WebSocket support needed for progress updates
- Filename convention for language: A03=lv, A04=ru, A05=en

**Codebase Map:**
- See `.planning/codebase/` for detailed architecture analysis

## Constraints

- **Tech stack**: React + Vite (Bun), embedded in existing FastAPI
- **Deployment**: Single container, no separate frontend service
- **Browser support**: Modern browsers (Chrome, Firefox, Safari, Edge)
- **Language detection**: Must support A03/A04/A05 filename convention

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Embed in FastAPI vs separate app | Simpler deployment, no CORS, single container | — Pending |
| React + Vite on Bun | User preference, modern tooling, fast builds | — Pending |
| WebSockets for progress | Better UX than polling for long transcriptions | — Pending |
| Filename-based language detection | User's existing workflow convention (A03/A04/A05) | — Pending |

---
*Last updated: 2026-01-27 after initialization*
