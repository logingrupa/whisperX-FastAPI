# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-29)

**Core value:** Users can sign up, get API keys, and use WhisperX via browser or external API with free-tier limits and Stripe-ready billing
**Current focus:** v1.2 — defining requirements

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-04-29 — Milestone v1.2 started (Multi-User Auth + API Keys + Billing-Ready)

## Performance Metrics

**Velocity (v1.1 final):**
- Total plans completed: 8 (v1.1)
- Average duration: 2.9 min
- Total execution time: 0.39 hours

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 7 | 3/3 | 10m | 3.3m |
| 8 | 3/4 | 7m | 2.3m |
| 9 | 2/3 | 7m | 3.5m |
| 10 | 0/2 | (deferred to v1.3) | — |

*Reset on each plan completion in v1.2.*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work (v1.1, carried forward):

- [v1.1 Research]: TUS protocol over custom chunking (mature libraries, proven patterns)
- [v1.1 Research]: 50MB chunk size (safe margin under Cloudflare 100MB limit)
- [v1.1 Research]: tuspyserver + tus-js-client stack (FastAPI native, comprehensive)
- [09-01]: Exponential backoff [1000, 2000, 4000] for TUS retry (3 attempts, RESIL-01)
- [09-01]: Permanent HTTP statuses (413, 415, 403, 410) never retried via onShouldRetry
- [09-02]: Cancel resets to pending (not error) so user can re-upload without retry flow

v1.2 entry decisions (locked from discuss with user 2026-04-29):

- Cookie session (httpOnly + secure + samesite=lax + 7d sliding) for browser; raw bearer `whsk_*` for external — middleware accepts both
- Argon2 password hashing
- Trial counter starts at first-key-created (not registration)
- Free tier: 5 req/hr + file <5min + 30min/day + tiny/small models only + 1 concurrent slot + back-of-queue
- Anti-DDOS: 3 register/hr per IP/24, 10 login/hr per IP/24
- Device fingerprint = cookie + ua hash + ip /24 + device_id (localStorage uuid)
- mailto password reset → `hey@logingrupa.lv` (no SMTP)
- Many API keys per user (named, scopes-ready, hashed)
- Self-serve `DELETE /api/account/data` (tasks + files, keeps user row)
- Stripe stub now: `Subscription`, `UsageEvent`, `plan_tier` enum, €5/mo "Pro" placeholder
- Tasks gain `user_id` FK; existing rows backfilled to admin user
- Alembic migrations introduced; baseline existing schema
- react-router-dom (already in deps) for `/login`, `/register`, `/dashboard/*` routes
- Vitest + React Testing Library + MSW for frontend test infra
- `/frontend-design` skill for all auth UI pages (super pro modern UI)
- Caveman mode passed to all subagents (token savings)

### Pending Todos

- None

### Blockers/Concerns

- Single shared `API_BEARER_TOKEN` middleware blocks frontend until v1.2 phase 1 ships
- tuspyserver fcntl patch is dev-only (Windows); production Linux is unaffected
- tuspyserver file.py patch (gc_files) needs reapplication after pip install
- Cloudflare WAF rules need validation in staging (deferred to v1.3)

## Session Continuity

Last session: 2026-04-29
Stopped at: v1.2 milestone start — defining requirements
Resume file: None
