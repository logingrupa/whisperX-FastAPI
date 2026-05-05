# WhisperX — Multi-Tenant SaaS

## What This Is

A production-ready web frontend + multi-tenant API for the WhisperX speech-to-text engine. Users self-register, get personal API keys, transcribe audio/video with speaker diarization, and export results — through the browser or directly via REST/WebSocket. Auth is cookie-session for the SPA + raw `whsk_*` Bearer tokens for external clients, both unified through a single `Depends(authenticated_user)` chain. Free-tier rate limits, 7-day trial, and Stripe-ready billing schema are all live; real Stripe integration is the v1.3 work.

## Core Value

Users can sign up, get personal API keys, transcribe audio/video with speaker identification, and export results — via browser or API — with usage gated by a free tier and (future) subscription plan.

## Current State (v1.2 shipped 2026-05-05)

- **10 phases delivered** (Phases 10-19), 62 plans, 111 tasks
- **Stack at close:** FastAPI 0.128 / Python 3.13, SQLite + Alembic, React 19 + Vite 7 + Bun, Vitest + RTL + MSW + Playwright
- **Auth shipped:** Argon2id passwords, HS256 JWT cookie session (sliding 7d), CSRF double-submit, `whsk_<8>_<22>` API keys (SHA-256 + indexed prefix lookup), CF-aware /24 rate limits, free-tier gates, Stripe schema stub
- **Phase 19 structural refactor** (post-cutover): dropped `dependency_injector`, moved auth to `Depends`, killed `AUTH_V2_ENABLED` + `DualAuthMiddleware` + `BearerAuthMiddleware` + `CsrfMiddleware`, single `Session` per request via `get_db`. 21/21 verification gates GREEN.
- **Test infrastructure:** vitest (138 tests) + Playwright (8 mocked specs + 3 real-backend Phase-19 specs) + pytest

## Next Milestone Goals (v1.3, planned)

To be defined via `/gsd-new-milestone`. Likely candidates:
- **Cloudflare e2e** — deferred from v1.1 phase 10 (TUS upload behind 100MB CF limit)
- **Real Stripe integration** — checkout, webhooks, customer portal (schema already in place)
- **Concurrency queue** — single-GPU prioritized worker, paid-tier front-of-queue
- **Phase 18 stretch items** — hCaptcha enable, HaveIBeenPwned password check, per-key scopes UI, per-key expiration
- **External binary observability** — surface ffmpeg / model presence in `/health` (lesson from v1.2 close-out: opaque 500 → guardrail → 503 + `FFMPEG_MISSING`)
- **Multi-worker rate-limit storage** — slowapi in-memory bucket → redis/limits (required before horizontal scale)
- **SMTP password reset** — currently `mailto:hey@logingrupa.lv` only

---

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**Pre-existing Backend:**
- ✓ REST API for speech-to-text transcription
- ✓ File upload endpoint (POST /speech-to-text)
- ✓ URL-based transcription (POST /speech-to-text-url)
- ✓ Task management (GET /tasks, GET /tasks/{id})
- ✓ Background processing with status tracking
- ✓ Speaker diarization integration
- ✓ Transcript alignment
- ✓ Webhook callbacks on completion
- ✓ Health check endpoints

**v1.0 Frontend UI (shipped 2026-01-29):**
- ✓ React frontend served at `/ui` route — v1.0
- ✓ Drag-and-drop file upload with multi-file queue — v1.0
- ✓ Real-time transcription progress via WebSockets — v1.0
- ✓ Auto-detect language from filename (A03=Latvian, A04=Russian, A05=English) — v1.0
- ✓ Transcript viewer with speaker labels and timestamps — v1.0
- ✓ Export to SRT, VTT, TXT, and JSON formats — v1.0
- ✓ Language and model selection dropdowns — v1.0
- ✓ File format validation with magic byte verification — v1.0

**v1.1 Chunked Uploads (shipped 2026-02-05):**
- ✓ TUS protocol resumable upload backend with tuspyserver — v1.1
- ✓ Server-side chunk reassembly and transcription trigger — v1.1
- ✓ 10-minute incomplete-session cleanup scheduler — v1.1
- ✓ TUS frontend client with file size routing (≥80MB → TUS) — v1.1
- ✓ Single smooth progress bar with speed (MB/s) and ETA — v1.1
- ✓ Exponential backoff retry [1s, 2s, 4s] with permanent-error classifier — v1.1
- ✓ Cancel button + retrying indicator + classified error wiring — v1.1
- ✓ localStorage-backed resume on page refresh — v1.1

**v1.2 Multi-User Auth + API Keys + Billing-Ready (shipped 2026-05-05):**
- ✓ Auth core — registration, login, session, logout, mailto password reset — v1.2
- ✓ API key management — issue, list, name, revoke; many per user — v1.2
- ✓ Dual auth — `Depends(authenticated_user)` chain accepts cookie session OR Bearer API key (Bearer wins) — v1.2 (Phase 19 collapsed dual middleware to single Depends)
- ✓ Per-user task scoping — `user_id` FK on tasks, `DELETE /api/account` cascade — v1.2
- ✓ Rate limiting + free tier gates — 5 req/hr, 7d trial, file/duration/model caps — v1.2
- ✓ Anti-DDOS — slowapi /24 IP bucket, register 3/hr, login 10/hr, device fingerprint — v1.2
- ✓ Stripe schema stub — `Subscription`, `UsageEvent`, `plan_tier` enum — v1.2
- ✓ Alembic migrations — baseline + 0002_auth_schema + 0003_tasks_user_id_not_null — v1.2
- ✓ Auth UI pages — login, register, dashboard/keys, dashboard/usage, account — v1.2
- ✓ Frontend test infrastructure — Vitest + RTL + MSW + Playwright — v1.2
- ✓ Admin bootstrap CLI — `python -m app.cli create-admin` + `backfill-tasks` — v1.2
- ✓ Phase 19 DI structural refactor — dropped `dependency_injector`, single `Session`/request, killed `AUTH_V2_ENABLED` flag — v1.2

### Active

<!-- Current scope. Building toward these. (Empty until /gsd-new-milestone runs.) -->

(none — between milestones; run `/gsd-new-milestone` to populate)

### Future

<!-- Deferred — valid but not in current milestone. -->

- Real Stripe integration (checkout, webhooks, customer portal) — v1.3 candidate (schema already in place)
- Single GPU concurrency queue/worker (priority queue, paid-tier front-of-queue) — v1.3 candidate
- SMTP email integration for password reset / verification — v1.3 candidate
- Cloudflare configuration + TUS e2e validation (was original v1.1 phase 10) — v1.3 candidate
- hCaptcha on register — v1.3 if abuse observed
- HaveIBeenPwned password check on register — v1.3 candidate
- Per-key scopes UI + per-key expiration — v1.3 candidate
- Multi-worker rate-limit storage (slowapi → redis/limits) — required before horizontal scale
- External binary observability surfaced in `/health` (ffmpeg, models) — v1.3 candidate
- Model management UI (view loaded models, download new) — backlog
- Step timing display after completion — backlog
- Responsive design improvements for tablet — backlog

### Out of Scope

- Mobile app — web-first, desktop/tablet focus
- Real-time streaming transcription — batch processing only
- Audio editing — transcription only, not an editor
- Inline transcript editing — complex state management, export to editor instead
- Video player with transcript sync — HTML5 video complexity

> **Evolution note (2026-04-29 → v1.2):** "User authentication — internal/trusted use" → moved to **Validated** (v1.2 delivered). "Multi-tenancy — single user/team deployment" → moved to **Validated** (per-user scoping + API keys delivered).

## Context

**Current State (post-v1.2, 2026-05-05):**
- v1.0 + v1.1 + v1.2 all shipped on `main`. Latest tag will be `v1.2`.
- Backend: FastAPI 0.128, Python 3.13, SQLite (records.db) + Alembic-managed schema, WhisperX 3.7.4, slowapi, Argon2-cffi, pyjwt, tuspyserver
- Frontend: React 19, Vite 7, Bun (lockfile `bun.lock`, no npm/yarn/pnpm), Tailwind v4, shadcn/ui, react-router-dom, zustand, react-hook-form + zod, Vitest + RTL + MSW, Playwright (Chromium)
- Communication: WebSocket (`/ws` with single-use 60s ticket from `/api/ws/ticket`), REST (`/auth/*`, `/api/*`, `/billing/*`, `/task/*`, `/speech-to-text*`), TUS (`/uploads/files/*`)
- Auth: cookie session (HS256 JWT, sliding 7d) + Bearer `whsk_*` keys; CSRF double-submit; CORS locked to `AUTH__FRONTEND_URL`
- Test surface at v1.2 close: 138 vitest, 8 Playwright (mocked) + 3 Playwright (real backend, Phase 19), pytest backend suite, plus Argon2 p99 benchmark (<300ms)
- Open lessons: ffmpeg is a hard runtime dep with no boot-time check (added guardrail in close-out commit `d15f958`); slowapi rate-limit needs `RATE_LIMIT_ENABLED=false` for repeated e2e runs (commit `d966b03`)
- 7 resolved debug sessions archived under `.planning/debug/resolved/` for reference

**Codebase Map:** see `.planning/codebase/` for detailed architecture analysis.

## Constraints

- **Tech stack**: React + Vite (Bun), embedded in existing FastAPI
- **Deployment**: Single container, no separate frontend service
- **Browser support**: Modern browsers (Chrome, Firefox, Safari, Edge)
- **Language detection**: Must support A03/A04/A05 filename convention
- **Package manager**: Bun only for all commands (no npm/yarn/pnpm)
- **Code principles**: SRP, DRY, tiger-style (assert at boundaries, no nested-if spaghetti)
- **UI components**: shadcn/ui + Radix only (no custom components)
- **Naming**: Full descriptive names only (no abbreviations like `btn`, `usr`, `msg`)
- **Communication**: caveman mode for all subagents and user-facing text (token efficiency)
- **No SMTP**: password reset is a `mailto:hey@logingrupa.lv` link only
- **DB**: SQLite `records.db`, WAL enabled, Alembic-managed migrations
- **Single Python interpreter**: `.venv` (uv-managed)
- **Production must enforce**: `RATE_LIMIT_ENABLED=true` (default), `AUTH__COOKIE_SECURE=true`, `AUTH__JWT_SECRET` + `AUTH__CSRF_SECRET` not at dev defaults

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Embed in FastAPI vs separate app | Simpler deployment, no CORS, single container | ✓ Good |
| React + Vite on Bun | User preference, modern tooling, fast builds | ✓ Good |
| WebSockets for progress | Better UX than polling for long transcriptions | ✓ Good |
| Filename-based language detection | User's existing workflow convention (A03/A04/A05) | ✓ Good |
| Tailwind v4 with CSS-first syntax | Modern approach, cleaner config | ✓ Good |
| Stage-based progress percentages | Transcription duration varies too much for time-based | ✓ Good |
| large-v3 as default model | User preference for accuracy over speed | ✓ Good |
| Discriminated union ApiResult<T> | Type-safe API results without exceptions | ✓ Good |
| Lazy load transcripts on expand | Avoids unnecessary API calls | ✓ Good |
| TUS protocol over custom chunking (v1.1) | Mature libraries, proven patterns | ✓ Good |
| 50MB chunk size (v1.1) | Safe margin under Cloudflare 100MB limit | ✓ Good |
| Defer Cloudflare e2e to v1.3 (v1.2 entry) | Auth blocks frontend NOW, must unblock first | ✓ Good (deferred) |
| Cookie session + Bearer API key dual auth (v1.2) | Browser ergonomics + external API ergonomics | ✓ Good |
| Argon2id password hashing (v1.2) | OWASP recommended, resistant to GPU attack | ✓ Good (p99=34.7ms) |
| Trial counter starts at first-key-created (v1.2) | Lazy users not penalized for late activation | ✓ Good |
| Stripe schema stub now, integration later (v1.2) | Avoid migration pain when billing goes live | ✓ Good (deferred to v1.3) |
| Alembic migrations introduced in v1.2 | Auth changes the schema, time to do this right | ✓ Good |
| Atomic backend+frontend cutover (Phase 13+14) | Half-shipping breaks app — backend without frontend 401s the SPA | ✓ Good (single deploy) |
| Single fetch site `apiClient.ts` (UI-11) | DRY auth/CSRF/redirect policy, grep-enforced | ✓ Good |
| BroadcastChannel('auth') for cross-tab logout | Native browser primitive, zero deps | ✓ Good |
| Phase 19 — drop `dependency_injector`, use `Depends` (v1.2) | DI lib introduced session-leak class twice; structural fix > whack-a-mole | ✓ Good (21/21 gates) |
| Single `Session` per request via `get_db` (Phase 19) | Eliminates session-leak class structurally | ✓ Good |
| Slowapi in-memory bucket OK for single-worker v1.2 | Acceptable for current scale; needs redis before multi-worker | ⚠️ Revisit at v1.3 |
| ffmpeg guardrail at boundary (v1.2 close-out) | Bare `subprocess.run(["ffmpeg",...])` produces opaque 500 on missing binary | ✓ Good |

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
*Last updated: 2026-05-05 after v1.2 milestone shipped*
