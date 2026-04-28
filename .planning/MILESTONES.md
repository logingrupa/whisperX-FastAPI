# Project Milestones: WhisperX Frontend UI

## v1.0 Frontend UI (Shipped: 2026-01-29)

**Delivered:** Production-ready web interface for audio/video transcription with real-time progress, speaker diarization, and multi-format export.

**Phases completed:** 1-6 (21 plans total)

**Key accomplishments:**

- WebSocket real-time progress system with stage indicators and reconnection handling
- Streaming upload infrastructure for large files (up to 5GB) with magic byte validation
- React SPA embedded in FastAPI at /ui with client-side routing
- Drag-and-drop upload UI with auto language detection from A03/A04/A05 filename patterns
- Live progress tracking with exponential backoff reconnection and polling fallback
- Transcript viewer with timestamps, speaker labels, and SRT/VTT/TXT/JSON export

**Stats:**

- 83 files created/modified
- 3,075 lines of TypeScript/TSX (frontend)
- 7 phases, 21 plans
- 3 days from start to ship (2026-01-27 → 2026-01-29)

**Git range:** `feat(01-01)` → `docs(05): complete`

**What's next:** v1.1 enhancements (upload progress with speed/ETA, step timing display, persistence on refresh) or new features.

---

## v1.1 Chunked Uploads (Shipped through Phase 9: 2026-02-05)

**Delivered:** TUS-protocol resumable chunked uploads — large files reach the backend through Cloudflare via 50MB chunks; resilient retry/cancel/resume on the frontend.

**Phases completed:** 7-9 (8 plans). Phase 10 (Cloudflare e2e) deferred to v1.3 because v1.2 auth retrofit blocks the frontend NOW.

**Key accomplishments:**

- TUS protocol resumable upload backend with tuspyserver
- Server-side chunk reassembly + transcription trigger hook
- 10-minute incomplete-session cleanup scheduler
- TUS frontend client with file size routing (≥80MB → TUS)
- Single smooth progress bar with speed (MB/s) + ETA
- Exponential backoff retry [1s, 2s, 4s] + permanent-error classifier
- Cancel button + retrying indicator + classified error UI
- localStorage-backed resume on page refresh

**Stats:**

- 8 plans across 3 phases
- Average plan duration: 2.9 minutes
- v1.1 phase 10 deferred → v1.3 (3 INTEG-* requirements)

**Git range:** `feat(07-01)` → `feat(09-02)`

**What's next:** v1.2 — multi-user auth retrofit (the deferred phase 10 follows in v1.3 once auth lands).

---

## v1.2 Multi-User Auth + API Keys + Billing-Ready (In progress — Started 2026-04-29)

**Target:** Convert trusted-deploy single-user app into multi-tenant SaaS with self-serve registration, per-user API keys, free-tier rate limits, and Stripe-ready billing schema.

**Target date:** TBD

**Status:** In progress — Roadmap created 2026-04-29; Phase 10 plan-phase next.

**Phases planned:** 10-18 (9 phases). Phases 13 + 14 deploy as **atomic pair**.

- Phase 10: Alembic Baseline + Auth Schema (silent infra)
- Phase 11: Auth Core Modules + Services + DI (silent infra)
- Phase 12: Admin CLI + Task Backfill (silent infra, pre-cutover)
- Phase 13: Atomic Backend Cutover **(ATOMIC PAIR with 14)**
- Phase 14: Atomic Frontend Cutover + Test Infra **(ATOMIC PAIR with 13)**
- Phase 15: Account Dashboard Hardening + Billing Stubs
- Phase 16: Verification + Cross-User Matrix + E2E
- Phase 17: Docs + Migration Runbook + Operator Guide
- Phase 18: Stretch (Optional)

**Requirements coverage:** 95/95 mapped (100%)

**Headline features:**

- Email/password registration + login (cookie session HS256 JWT, 7d sliding, CSRF-protected)
- Argon2id password hashing (OWASP `m=19456 KiB, t=2, p=1`)
- Per-user API keys (`whsk_<prefix>_<random>`, sha256-hashed, prefix-indexed)
- Dual-auth middleware (cookie session + bearer API key)
- Per-user task scoping (`tasks.user_id` FK + repository-layer WHERE filter)
- IP-locked register/login throttling (3/hr + 10/hr per /24)
- Device fingerprint logging
- Free-tier gates (5 req/hr, 5min file, 30min/day, tiny/small models only, 7d trial)
- Stripe-ready schema (Subscription, UsageEvent, plan_tier enum) — €5/mo Pro stub
- Alembic migrations replace `Base.metadata.create_all()`
- Auth UI pages (login, register, dashboard/keys, dashboard/usage, dashboard/account)
- Vitest + RTL + MSW frontend test infra
- Bootstrap admin CLI (`python -m app.cli create-admin`)

**Git range:** TBD

**What's next (post-v1.2 → v1.3):** Real Stripe integration (FUTURE-01), single-GPU concurrency queue (FUTURE-02), Cloudflare e2e validation (FUTURE-03 — was v1.1 phase 10), SMTP email (FUTURE-04).

---
*Last updated: 2026-04-29 — v1.2 roadmap appended (Multi-User Auth + API Keys + Billing-Ready, 9 phases 10-18)*
