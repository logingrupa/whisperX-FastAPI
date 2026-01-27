# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-27)

**Core value:** Users can easily upload audio, transcribe with speaker identification, and export results — without touching the command line or API directly.
**Current focus:** Phase 5 - Real-time Progress Tracking

## Current Position

Phase: 5 of 6 (Real-time Progress Tracking)
Plan: 1 of 4 in current phase
Status: In progress
Last activity: 2026-01-27 - Completed 05-01-PLAN.md (Foundation Types and Components)

Progress: [████████░░] 82%

## Performance Metrics

**Velocity:**
- Total plans completed: 12
- Average duration: 4.5 min
- Total execution time: 0.95 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-websocket-task-infrastructure | 2/2 | 12 min | 6 min |
| 02-file-upload-infrastructure | 2/2 | 13 min | 6.5 min |
| 03-build-integration-spa-serving | 3/3 | 12 min | 4 min |
| 04-core-upload-flow | 4/4 | 15 min | 3.75 min |
| 05-real-time-progress-tracking | 1/4 | 2 min | 2 min |

**Recent Trend:**
- Last 5 plans: 04-02 (2 min), 04-03 (3 min), 04-04 (5 min), 05-01 (2 min)
- Trend: Consistent, fast execution

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Bun only for package management
- shadcn/ui + Radix components only (no custom components)
- SRP and DRY principles enforced
- Full descriptive names (no abbreviations)
- Individual file downloads (not ZIP)

**Phase 1 decisions:**
- Reorganized app/schemas.py into app/schemas/ package to avoid import collision
- Used Literal types for WebSocket message type fields
- 30-second heartbeat interval per research recommendation
- Stage-based progress percentages (not time-based) per research recommendation
- Lazy singleton for ProgressEmitter to avoid circular imports

**Phase 2 decisions:**
- Use streaming-form-data library for memory-efficient multipart parsing (Cython-optimized)
- 5GB max file size with early rejection during upload (not after)
- Store uploads in system temp directory (gettempdir() / whisperx_uploads)
- Separate upload_config.py module to avoid circular imports with main Config
- Magic validation happens after upload completes (need full header for reliable detection)
- 8KB header read for reliable magic byte detection
- Canonical extension mapping normalizes variants (.oga -> .ogg, .m4v -> .mp4)

**Phase 3 decisions:**
- Bun for package management (bunx create-vite, bun install)
- Tailwind v4 with @tailwindcss/vite plugin (not PostCSS)
- CSS-first syntax: @import "tailwindcss" instead of @tailwind directives
- Skeleton as sibling of #root for CSS :not(:empty) selector
- @/* path alias for all src/ imports (shadcn/ui convention)
- Mount static assets at /ui/assets BEFORE catch-all routes
- SPA catch-all route registered AFTER all API routes in main.py
- Index.html uses relative paths, Vite base config adds /ui/ prefix during build

**Phase 4 decisions:**
- 16 languages total: 3 core (lv, ru, en) + 13 common European/Asian languages
- A03/A04/A05 pattern detection is case-insensitive
- large-v3 as default Whisper model (user preference for accuracy)
- Types in frontend/src/types/, utilities in frontend/src/lib/
- Manual shadcn/ui setup due to Tailwind v4 incompatibility with CLI
- Fixed sonner component to use sonner package instead of next-themes
- TooltipProvider at root for performance (not per-tooltip)
- Hooks in frontend/src/hooks/ directory
- Upload components in frontend/src/components/upload/ directory
- noClick pattern for full-page drop targets (react-dropzone)
- removeFile only removes pending files (per CONTEXT.md constraint)

**Phase 5 decisions:**
- Continued manual shadcn/ui component creation (Tailwind v4 CLI incompatibility)
- WebSocket types mirror backend schemas exactly for type safety
- Stage configuration provides friendly names and colors per CONTEXT.md

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-01-27T17:56:35Z
Stopped at: Completed 05-01-PLAN.md (Foundation Types and Components)
Resume file: None
