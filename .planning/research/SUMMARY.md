# Project Research Summary — v1.2 Multi-User Auth + API Keys + Billing-Ready

**Project:** WhisperX FastAPI App
**Domain:** Multi-tenant SaaS auth retrofit onto existing single-user FastAPI/SQLite/React app
**Researched:** 2026-04-29
**Confidence:** HIGH

## Executive Summary

v1.2 converts trusted-deploy single-user app to multi-tenant SaaS. Bolt-on auth, not rewrite. Foundation: cookie session (HS256 JWT) + raw API key (`whsk_*`) dual-auth on ONE middleware. Argon2id passwords. Double-submit CSRF. SQLite-backed token bucket rate limit. Alembic migrations replace `Base.metadata.create_all()`. Stripe schema stub (no integration). Frontend gets router shell, auth pages, central `apiClient` wrapper, Vitest+RTL+MSW test infra.

Recommended: **9 atomic phases**, silent infra (10-12) → atomic backend+frontend cutover (13+14) → polish/verify (15-17) → optional stretch (18). Stack consolidated from all four researchers: argon2-cffi 25.1.0, PyJWT 2.12.1 (NOT python-jose — abandoned, FastAPI docs migrated), fastapi-csrf-protect 0.3.3, slowapi 0.1.9, alembic 1.18.4, stripe 15.1.0, typer 0.24.2; frontend zustand 5, react-hook-form 7.60, zod 3.25, vitest 3.2, RTL 16.1, MSW 2.13.

Top risks: (a) `tasks.user_id` FK backfill on populated `records.db` requires 3-step nullable→backfill→NOT NULL via batch_alter_table; (b) WS `/ws/tasks/{task_id}` zero-auth = cross-user leak — fix with single-use ticket query param NOT subprotocol (Cloudflare strips); (c) `Base.metadata.create_all()` at `app/main.py:48` must die same commit Alembic ships; (d) `allow_origins=["*"]` at `app/main.py:174` incompatible with cookie credentials — explicit allowlist mandatory; (e) Argon2 default `m_cost=65536` = login DoS — use OWASP `m=19456, t=2, p=1`; (f) per-user task scoping single missed `WHERE user_id` = data leak.

## Conflict Resolutions (Researcher Disagreements)

| Topic | ARCHITECTURE proposed | PITFALLS proposed | Decision | Rationale |
|-------|----------------------|-------------------|----------|-----------|
| WS auth transport | `Sec-WebSocket-Protocol` subprotocol | Single-use 60s ticket query param | **Ticket query param** | Cloudflare/some nginx/AWS ALB strip non-standard subprotocols silently. v1.3 Cloudflare prod target. Single-use, short-lived → URL-log leak window minimal. |
| Rate-limit storage | SQLite token bucket + `BEGIN IMMEDIATE` | SQLite token bucket + `BEGIN IMMEDIATE` | **CONFIRMED** | WAL on. Worker-safe. Single-container = no Redis. Load test in Phase 16 to validate write-contention. |
| Phase count | 8 phases | 9 phases (numbered 11-19) | **9 phases (10-18)** | Splitting admin CLI + frontend test infra + verification + docs as distinct phases is cleaner. v1.1 phase 10 (Cloudflare) deferred to v1.3 → resume numbering at 10. |
| Stack libs | argon2-cffi, PyJWT, alembic, slowapi, vitest, MSW, RTL, zustand, RHF, zod | Same | **CONFIRMED — STACK.md table is canonical** | All 4 researchers aligned. python-jose explicitly rejected (abandoned ~3yr). |

## Key Findings

### Recommended Stack (Consolidated)

Existing stack stays. Adds 7 backend libs, 11 frontend. No replacements.

| Layer | Package | Version | Purpose |
|-------|---------|---------|---------|
| Auth core | argon2-cffi | 25.1.0 | Argon2id password hash (OWASP) |
| Auth core | PyJWT | 2.12.1 | JWT sign/verify (replaces python-jose) |
| CSRF | fastapi-csrf-protect | 0.3.3 | Double-submit cookie via `Depends` |
| Rate limit | slowapi | 0.1.9 | Sliding-window, custom key_func |
| Migrations | alembic | 1.18.4 | Replaces `create_all()`; baseline workflow |
| Billing stub | stripe | 15.1.0 | Schema-only, no runtime integration |
| CLI | typer | 0.24.2 | `python -m app.cli create-admin` |
| Frontend state | zustand | ^5.0.12 | Auth store (avoids Context re-render) |
| Frontend forms | react-hook-form, zod, @hookform/resolvers | ^7.60.0, ^3.25.76, ^5.1.1 | Forms + validation |
| Frontend test runner | vitest, @vitest/ui, jsdom | ^3.2.0, ^3.2.0, ^29.0.2 | Vite 7 needs vitest ≥3.2 |
| Frontend test utils | @testing-library/react, user-event, jest-dom | ^16.1.0, ^14.6.1, ^6.6.3 | Component test utils |
| Frontend mocking | msw | ^2.13.4 | API mocking |

Stdlib only: `hashlib` (fingerprint sha256), `secrets` (api key gen + `compare_digest`), `datetime`/`timezone` (JWT exp).

**Avoid:** python-jose, passlib, bcrypt for new hashes, fastapi-users, fastapi-limiter, redis, formik, yup, happy-dom, jotai, react-redux.

### Expected Features

**Must have (P1, all in v1.2):** single-page register/login (generic-error enumeration prevention), HttpOnly+Secure+SameSite=Lax cookie session 7d sliding, logout-all-devices via `token_version`, API key UI (list/create-show-once/copy/revoke/soft-delete), free-tier counter visible, trial countdown banner, 429 retry-after UX, account dashboard with delete-account (type-email), IP throttle 3/hr register + 10/hr login per /24, device fingerprint, CSRF invisible double-submit, Pro upgrade stub + interest-capture modal.

**Should have (defer v1.3):** email verification (needs SMTP), magic link login, per-key scopes UI, per-key expiration, active sessions list, usage charts, HaveIBeenPwned check, hCaptcha (env-flagged stub now).

**Defer v2+:** TOTP 2FA, WebAuthn, team plans, refresh token rotation, email change flow.

**Anti-features (do NOT build):** multi-step register wizard, required phone, username field, localStorage JWT, fake "Subscribe" button, custom payment form, GET endpoints that mutate, security questions, forced password rotation, plaintext API key storage, `?api_key=` query param.

### Architecture Approach

Bolt-on auth onto existing DI/repo conventions. Single `DualAuthMiddleware` replaces `BearerAuthMiddleware` at `app/core/auth.py` — same import, same registration site (`main.py:169`). Sets `request.state.user`, `.plan_tier`, `.auth_method`, `.api_key_id`. Per-user filtering at REPOSITORY layer (NOT API layer) — `ITaskRepository.set_user_scope(user_id)` pushes filter into SQL `WHERE`. CSRF via `Depends(verify_csrf)` route-level (NOT middleware) — bearer routes early-return. WebSocket auth via single-use ticket (60s TTL) query param + ownership check before `accept()`.

**Major components:**
1. `app/core/auth.py` `DualAuthMiddleware` — bearer→cookie→public resolution
2. `app/core/jwt_codec.py` (single source) — `algorithms=["HS256"]` hard-coded
3. `app/core/api_key.py` (single source) — `whsk_<8-prefix>_<32-rand>`, sha256, prefix-indexed lookup, `secrets.compare_digest`
4. `app/core/auth_cookies.py` (single source) — env-driven `Secure`, `HttpOnly`, `SameSite=Lax`
5. `app/services/{auth,key,rate_limit,csrf}_service.py`
6. `app/infrastructure/database/repositories/sqlalchemy_*_repository.py` — User/ApiKey/RateLimitBucket/Subscription/UsageEvent
7. Alembic migrations at `app/infrastructure/database/migrations/`
8. `frontend/src/lib/apiClient.ts` — single fetch wrapper
9. `frontend/src/components/auth/{AuthProvider,ProtectedRoute}.tsx` + zustand + react-router
10. `app/cli.py` Typer CLI

### Critical Pitfalls (Top 5)

1. **`tasks.user_id` FK backfill on populated DB** — 3-step migration: nullable add → Typer backfill assigning admin → `batch_alter_table` NOT NULL + FK CASCADE. Delete `Base.metadata.create_all()` from `app/main.py:48` same commit. Smoke-test against `records.db` copy.
2. **WS cross-user task leak** — Current `/ws/tasks/{task_id}` zero-auth. Pattern: `POST /api/ws/ticket` (cookie/API key auth) → 60s one-time ticket → WS connects `?ticket=...` → server consumes + verifies `ticket.user_id == task.user_id` BEFORE `accept()`. Rejects subprotocol (CF strips).
3. **JWT alg=none + algorithm confusion** — `algorithms=["HS256"]` mandatory. Single decode site `app/core/jwt_codec.py`. Test alg=none → 401, tampered → 401, expired → 401. Lint: `import jwt` allowed only in jwt_codec.
4. **CORS `allow_origins=["*"]` + cookies** — Browser silently rejects wildcard with credentials. `app/main.py:174` env-driven explicit allowlist + `allow_credentials=True`.
5. **Per-user task scoping single missed `WHERE`** — Refactor `ITaskRepository`: every method takes `user_id`. Two-user fixtures in EVERY task test. Audit checklist becomes acceptance criteria. Endpoints to audit: `GET/DELETE /tasks`, `POST /speech-to-text*`, `tus_upload_api`, `websocket_api`, `callbacks`, `DELETE /api/account/data`.

Honorable mentions: Argon2 m_cost too high → DoS (use `m=19456, t=2, p=1`); SameSite=Lax 2-min Chrome grace + GET state-change (lint: `@router.get` is read-only); rate-limit IPv6 /128 vs /64 (custom key_func with CF-Connecting-IP + /24 IPv4 + /64 IPv6); Stripe schema baked NOW (`plan_tier` enum CHECK, `idempotency_key UNIQUE NOT NULL`, `cancelled_at` soft-delete, `DateTime(timezone=True)` everywhere); auth code duplication (single `auth_resolver.py`).

## Roadmap Implications (9 Phases, numbered 10-18)

### Phase 10 — Alembic Baseline + Auth Schema (Silent Infra)

Schema foundation. Zero behavior change. Replaces `Base.metadata.create_all()`.

Delivers: alembic init, hand-written baseline mirroring current `tasks` schema, `alembic stamp head` on prod, migration adding User/ApiKey/Subscription/UsageEvent/RateLimitBucket/DeviceFingerprint, migration adding `tasks.user_id NULLABLE`, PRAGMA foreign_keys=ON listener, naming convention, DELETE `create_all()` line.

### Phase 11 — Auth Core Modules + Domain + Services + DI (Silent Infra)

Pure logic, unit-testable, no HTTP exposure.

Delivers: Domain entities + repos, jwt_codec.py (single decode), api_key.py (single source), auth_cookies.py (env-driven), auth/key/rate_limit/csrf services, argon2 + JWT infrastructure, DI container wiring (mirrors existing pattern), Argon2 benchmark test <300ms p99.

### Phase 12 — Admin CLI + Task Backfill (Pre-cutover)

Must seed admin + backfill orphan tasks BEFORE auth gate (Phase 13). Otherwise NOT NULL migration fails.

Delivers: `app/cli.py` Typer commands `create-admin`, `backfill-tasks`; backfill UPDATE migration; `batch_alter_table` NOT NULL + FK CASCADE migration; `idx_tasks_user_id`. Verify against COPY of prod `records.db`.

### Phase 13 — ATOMIC Cutover (Backend)

**Big one — must ship atomic with Phase 14.** Half-shipping breaks app.

Delivers: DualAuthMiddleware replaces BearerAuthMiddleware; auth/account/keys routes; per-user task scoping refactor across ALL endpoints; WS ticket flow (`POST /api/ws/ticket` → `?ticket=`); TUS upload auth (API-key or cookie+CSRF); CSRF `Depends(verify_csrf)` on session state-mutating routes; CORS lockdown explicit allowlist + `allow_credentials=True`; slowapi with custom key_func (CF-Connecting-IP + /24 + /64); device fingerprint; SQLite token bucket rate-limit; free-tier gates (5 req/hr, file/duration/model caps); UsageEvent log; disposable-email blocklist; hCaptcha hook scaffolded env-off.

### Phase 14 — ATOMIC Cutover (Frontend) + Test Infra

Frontend auth UI must be live the moment Phase 13 lands. Existing SPA's raw `fetch('/task/...')` returns 401 instantly otherwise.

Delivers: `BrowserRouter basename="/ui"`; routes `/login`, `/register`, `/dashboard/{keys,usage,account}`; existing UploadDropzone moves verbatim to `routes/TranscribePage.tsx`; AuthProvider + ProtectedRoute + zustand store; `lib/apiClient.ts` single fetch wrapper (CSRF inject + 401 redirect); migrate `taskApi`, `transcriptionApi`, `tusUpload`, `useTaskProgress` through apiClient; Vitest + RTL + MSW infra (`vitest.config.ts`, single `setup.ts`, `msw init public/`); login/register/dashboard pages with react-hook-form + zod + shadcn `<Form>`; API key list/create-modal-show-once/revoke; free-tier counter; trial banner; 429 inline countdown; BroadcastChannel('auth') cross-tab logout sync.

### Phase 15 — Stripe Schema Polish + Account Dashboard Hardening

Post-cutover stability. Pure additive.

Delivers: Plan tier card, billing history empty state, delete-account flow type-email two-step, "Upgrade to Pro" + plan comparison + interest-capture modal, logout-all-devices button, active sessions list.

### Phase 16 — Verification + E2E + Cross-User Matrix Tests

Gate to milestone close.

Delivers: Cross-user matrix tests for all task endpoints; WS ticket flow integration test; Argon2 benchmark CI; JWT alg=none rejection test; CSRF stale-token recovery test; rate-limit IP/proxy test; multi-tab BroadcastChannel test (Playwright); migration smoke test; "Looks Done But Isn't" checklist closed.

### Phase 17 — Docs + Migration Runbook + Operator Guide

Delivers: `.env.example` updates (JWT_SECRET, CSRF_SECRET, COOKIE_*, RATE_LIMIT_*, ARGON2_*, CF_TRUST_HEADER); README updates; migration runbook (backup → stamp → upgrade → verify); admin CLI docs; OpenAPI updates; threat model snapshot.

### Phase 18 — Stretch (Optional)

Delivers: hCaptcha enable, HaveIBeenPwned k-anonymity, per-key scopes UI, per-key expiration date picker.

### Phase Ordering Rationale

- **10-12 silent infra** — ship serially without user impact. Schema → services → admin CLI (CLI requires services + nullable column).
- **13+14 atomic** — single deploy. Build on branch, test e2e behind feature flag, flip together.
- **15 polish** — additive dashboard surfaces.
- **16 verification** — milestone close gate; all 20 pitfalls show prevention evidence.
- **17 docs** — parallel with 16 in practice.
- **18 stretch** — explicitly optional.

### Research Flags

**Needs deeper research (`/gsd-research-phase`):**
- **Phase 10** — Alembic baseline against populated SQLite, batch_alter_table mechanics, naming conventions for stable downgrade, tuspyserver tables in same DB
- **Phase 12** — Migration ordering, CASCADE behavior on SQLite, FK pragma per-connection
- **Phase 13** — LARGEST + MOST CRITICAL. WS ticket TTL cleanup, slowapi custom key_func + CF IP range validation, fastapi-csrf-protect bearer-exempt branch, TUS upload header CSRF, dual-auth middleware ordering with CORS preflight
- **Phase 14** — react-router-dom 7 `BrowserRouter basename` with FastAPI catch-all SPA mount, MSW v2 syntax, zustand selector for auth, BroadcastChannel coordination, tus-js-client headers injection

**Standard patterns (skip):** Phases 11, 15, 16, 17, 18

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified PyPI/npm 2026-04; cross-validated FastAPI docs, OWASP, Vite 7 release |
| Features | HIGH | Cross-validated 5+ products (Stripe/Vercel/Linear/Cloudflare/GitHub/OpenAI/Resend) |
| Architecture | HIGH | Codebase grep-verified every integration point with line numbers |
| Pitfalls | HIGH | OWASP cheats + Alembic docs + slowapi docs + recent CVEs (2025-68402, 2022-29217, 2026-22817) + codebase grep |

**Overall:** HIGH

### Gaps to Address During Planning

- WS ticket cleanup TTL strategy — SQLite-backed for worker-safety; cleanup background task. Resolve in Phase 13 planning.
- Cloudflare IP allowlist for `CF-Connecting-IP` — bundle CF ranges OR trust deploy config (env flag `TRUST_CF_HEADER=true`). Resolve in Phase 13.
- Argon2 prod-hardware benchmark — single-VPS deploy; capture hardware spec in `.env.example` + CI benchmark. Resolve in Phase 11.
- TUS cookie auth vs API-key-only — recommend cookie+CSRF for browser path, API key for external. Resolve in Phase 13.
- SQLite write contention — WAL on already. Validation: load test 50 concurrent logins + 50 concurrent transcribe in Phase 16.
- React 19 + RTL 16 `act()` warnings — pre-emptive: `await user.click()` everywhere, `findByRole` not `getByRole`. Document in `src/tests/setup.ts`.
- `AUTH_V2_ENABLED` feature flag scope — module-import env check → restart needed to flip. Acceptable for staged rollout.

---

## Roadmap Implications Recap

**9 phases** numbered 10-18. v1.1 phase 10 (Cloudflare) deferred to v1.3.

1. **Phase 10** — Alembic Baseline + Auth Schema
2. **Phase 11** — Auth Core Modules + Services + DI
3. **Phase 12** — Admin CLI + Task Backfill
4. **Phase 13** — Atomic Backend Cutover (DualAuthMiddleware + routes + scoping + WS ticket + CSRF + CORS + rate-limit)
5. **Phase 14** — Atomic Frontend Cutover + Test Infra (must ship with Phase 13)
6. **Phase 15** — Stripe Polish + Dashboard Hardening
7. **Phase 16** — Verification + E2E + Cross-User Matrix
8. **Phase 17** — Docs + Runbook + Operator Guide
9. **Phase 18** — Stretch (Optional)

**Critical: Phases 13 + 14 must deploy atomically.**
