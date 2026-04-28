# WhisperX Frontend UI

## What This Is

A production-ready web frontend for the WhisperX speech-to-text API. Users can upload audio/video files, transcribe them with speaker diarization, and export results in multiple formats. The UI is embedded in FastAPI and served at `/ui`.

As of v1.2, the application is evolving into a multi-tenant SaaS: self-serve registration, per-user API keys, free-tier rate limits, and Stripe-ready billing infrastructure.

## Core Value

Users can sign up, get personal API keys, transcribe audio/video with speaker identification, and export results — via the browser or via API — with usage gated by a free tier and (future) subscription plan.

## Current Milestone: v1.2 Multi-User Auth + API Keys + Billing-Ready

**Goal:** Transform single-user trusted deployment into multi-tenant SaaS with self-serve registration, API keys, free-tier rate limiting, and Stripe-ready billing infrastructure.

**Target features:**
- Email/password registration (open) and login with cookie session (7d sliding JWT, CSRF-protected)
- Argon2 password hashing
- Per-user API key management (many keys, scopes-ready, hashed `whsk_*` format)
- Bearer auth middleware accepting both cookie session and raw API key
- Per-user task scoping with self-serve `DELETE /api/account/data`
- IP-locked register (3/hr per /24) and login (10/hr per /24) for anti-spam/anti-DDOS
- Device fingerprint logging (cookie + ua hash + ip /24 + device_id)
- Free tier: 5 req/hour, 7-day trial from first key creation, file/duration/model gates
- Stripe-ready schema (`Subscription`, `UsageEvent`, `plan_tier` enum) — €5/mo Pro placeholder
- Alembic migrations init + baseline of existing schema
- Frontend auth pages (login, register, dashboard/keys, dashboard/usage) via `/frontend-design`
- Vitest + React Testing Library + MSW frontend test infrastructure
- Bootstrap admin CLI (`python -m app.cli create-admin`)
- mailto password reset link → `hey@logingrupa.lv` (no SMTP)

---

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

**v1.1 Chunked Uploads (shipped through phase 9, 2026-02-05):**
- TUS protocol resumable upload backend with tuspyserver — v1.1
- Server-side chunk reassembly and transcription trigger — v1.1
- 10-minute incomplete-session cleanup scheduler — v1.1
- TUS frontend client with file size routing (≥80MB → TUS) — v1.1
- Single smooth progress bar with speed (MB/s) and ETA — v1.1
- Exponential backoff retry [1s, 2s, 4s] with permanent-error classifier — v1.1
- Cancel button + retrying indicator + classified error wiring — v1.1
- localStorage-backed resume on page refresh — v1.1

### Active

<!-- Current scope. Building toward these. -->

- [ ] **Auth core** — registration, login, session, logout, password reset (mailto)
- [ ] **API key management** — issue, list, name, revoke; many per user
- [ ] **Dual auth middleware** — cookie session + bearer API key
- [ ] **Per-user task scoping** — `user_id` FK on tasks, account data delete
- [ ] **Rate limiting + free tier gates** — 5 req/hr, 7d trial, file/duration/model caps
- [ ] **Anti-DDOS** — IP-lock, device fingerprint, register-throttle
- [ ] **Stripe schema stub** — `Subscription`, `UsageEvent`, `plan_tier` placeholder
- [ ] **Alembic migrations** — initialize + baseline current schema
- [ ] **Auth UI pages** — login, register, dashboard/keys, dashboard/usage
- [ ] **Frontend test infrastructure** — Vitest + RTL + MSW
- [ ] **Admin bootstrap CLI** — `python -m app.cli create-admin`

### Future

<!-- Deferred — valid but not in current milestone. -->

- v1.1 Cloudflare configuration + e2e validation (was original phase 10) — defer to v1.3
- Real Stripe integration (checkout, webhooks, customer portal) — v1.3 after schema stub proven
- Single GPU concurrency queue/worker (priority queue, paid-tier front-of-queue) — v1.3
- SMTP email integration for password reset / verification — v1.3
- Hcaptcha on register — v1.3 if abuse observed
- Model management UI (view loaded models, download new) — backlog
- Step timing display after completion — backlog
- Responsive design improvements for tablet — backlog

### Out of Scope

- Mobile app — web-first, desktop/tablet focus
- Real-time streaming transcription — batch processing only
- Audio editing — transcription only, not an editor
- Inline transcript editing — complex state management, export to editor instead
- Video player with transcript sync — HTML5 video complexity

> **Evolution note (2026-04-29 → v1.2):**
> "User authentication — internal/trusted use for now" → moved to **Active** (this milestone delivers it)
> "Multi-tenancy — single user/team deployment" → moved to **Active** (per-user task scoping + API keys deliver it)

## Context

**Current State (entering v1.2, 2026-04-29):**
- v1.0 + v1.1 (through phase 9) shipped — frontend + chunked uploads
- Phase 10 (Cloudflare e2e) deferred to v1.3
- Backend has single shared `API_BEARER_TOKEN` env var middleware → blocks frontend, blocks multi-user
- SQLite `records.db` with single `tasks` table, no users table
- Frontend has zero `Authorization` header injection
- `react-router-dom@7.13` already in deps (unused)

**Tech Stack:**
- Backend: FastAPI 0.128, Python 3.11, SQLite (records.db), WhisperX 3.7.4
- Frontend: React 19, Vite 7, Bun, Tailwind v4, shadcn/ui
- Communication: WebSocket for progress, REST for CRUD, TUS for chunked upload
- New for v1.2: argon2-cffi, python-jose (JWT), alembic, slowapi, vitest, MSW, react-router-dom (already installed)

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
- **Communication**: caveman mode for all subagents and user-facing text (token efficiency)
- **No SMTP**: password reset is a `mailto:hey@logingrupa.lv` link only
- **DB**: reuse existing `records.db` SQLite, enable WAL for concurrent webhook + request writes

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
| TUS protocol over custom chunking (v1.1) | Mature libraries, proven patterns | Good |
| 50MB chunk size (v1.1) | Safe margin under Cloudflare 100MB limit | Good |
| Defer Cloudflare e2e to v1.3 (v1.2 entry) | Auth blocks frontend NOW, must unblock first | Pending |
| Cookie session + bearer API key dual auth (v1.2) | Browser ergonomics + external API ergonomics | Pending |
| Argon2 password hashing (v1.2) | OWASP recommended, resistant to GPU attack | Pending |
| Trial counter starts at first-key-created (v1.2) | Lazy users not penalized for late activation | Pending |
| Stripe schema stub now, integration later (v1.2) | Avoid migration pain when billing goes live | Pending |
| Alembic migrations introduced in v1.2 | Auth changes the schema, time to do this right | Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-29 — v1.2 milestone start (Multi-User Auth + API Keys + Billing-Ready)*
