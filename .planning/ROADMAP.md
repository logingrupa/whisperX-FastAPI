# Roadmap: WhisperX v1.2 Multi-User Auth + API Keys + Billing-Ready

## Milestones

- [x] **v1.0 Frontend UI** — Phases 1-6 (shipped 2026-01-29)
- [x] **v1.1 Chunked Uploads** — Phases 7-9 (shipped through phase 9, 2026-02-05; phase 10 Cloudflare deferred to v1.3)
- [ ] **v1.2 Multi-User Auth + API Keys + Billing-Ready** — Phases 10-18 (in progress)

## Overview

v1.2 converts the trusted-deploy single-user app into a multi-tenant SaaS. Bolt-on auth — not rewrite. Foundation: cookie session (HS256 JWT) + raw API key (`whsk_*`) dual-auth in ONE middleware. Argon2id passwords. Double-submit CSRF. SQLite-backed token-bucket rate limit. Alembic migrations replace `Base.metadata.create_all()`. Stripe schema stub (no integration). Frontend gets router shell, auth pages, central `apiClient` wrapper, Vitest+RTL+MSW test infra.

## Phases

**Phase Numbering:**
- Integer phases (10-18): Planned v1.2 work
- Decimal phases (e.g. 13.1): Reserved for urgent insertions via `/gsd-insert-phase`
- v1.1 phase 10 (Cloudflare e2e) deferred to v1.3 — v1.2 resumes integer numbering at 10

- [x] **Phase 10: Alembic Baseline + Auth Schema** — Replace `create_all()` with hand-written baseline + auth/billing/rate-limit tables; zero behavior change (completed 2026-04-29)
- [ ] **Phase 11: Auth Core Modules + Services + DI** — Pure logic modules (jwt_codec, api_key, password hasher, services, DI providers); HTTP-untouched
- [ ] **Phase 12: Admin CLI + Task Backfill** — Typer CLI seeds admin user + backfills `tasks.user_id`; FK NOT NULL constraint applied last
- [ ] **Phase 13: Atomic Backend Cutover (ATOMIC PAIR with Phase 14)** — DualAuthMiddleware + auth/keys/account routes + per-user scoping + WS ticket + CSRF + CORS lockdown + rate-limit + free-tier gates + Stripe schema stubs
- [ ] **Phase 14: Atomic Frontend Cutover + Test Infra (ATOMIC PAIR with Phase 13)** — Router shell + auth pages + dashboard (keys/usage) + apiClient wrapper + zustand store + BroadcastChannel + Vitest/RTL/MSW
- [ ] **Phase 15: Account Dashboard Hardening + Billing Stubs** — Account page (delete + logout-all-devices + Pro upgrade CTA) + checkout/webhook 501 stubs
- [ ] **Phase 16: Verification + Cross-User Matrix + E2E** — Cross-user tests + JWT attack tests + WS ticket reuse + CSRF mismatch + migration smoke against records.db
- [ ] **Phase 17: Docs + Migration Runbook + Operator Guide** — `.env.example`, README auth flow, migration runbook, OpenAPI updates
- [ ] **Phase 18: Stretch (Optional)** — hCaptcha enable, HaveIBeenPwned check, per-key scopes UI, per-key expiration

## Phase Details

### Phase 10: Alembic Baseline + Auth Schema
**Goal**: Schema foundation — Alembic owns migrations, auth/billing/rate-limit tables exist, `tasks.user_id` exists nullable; zero observable behavior change.
**Depends on**: v1.1 Phase 9 complete
**Requirements**: SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, SCHEMA-05, SCHEMA-06, SCHEMA-07, SCHEMA-08
**Success Criteria** (what must be TRUE):
  1. Operator runs `alembic stamp head` against existing `records.db` and `alembic current` reports the baseline revision without modifying existing `tasks` rows
  2. Operator runs `alembic upgrade head` and `users`, `api_keys`, `subscriptions`, `usage_events`, `rate_limit_buckets`, `device_fingerprints` tables exist; `tasks` has nullable `user_id` column with named FK constraint
  3. `Base.metadata.create_all()` is gone from `app/main.py`; app boots cleanly using migrations as source of truth
  4. Every connection enforces `PRAGMA foreign_keys = ON` (verified by querying `PRAGMA foreign_keys` after connect); every datetime column declares `DateTime(timezone=True)`
  5. `Subscription.plan_tier` rejects values outside the enum CHECK; `usage_events.idempotency_key` rejects duplicates with UNIQUE violation
**Plans**: 4 plans (3 waves)
- [x] 10-01-PLAN.md — Alembic install + scaffolding + 0001_baseline empty stamp revision (Wave 1)
- [x] 10-02-PLAN.md — ORM models extension: 6 new classes + tasks.user_id + DRY column factories (Wave 2)
- [x] 10-03-PLAN.md — 0002_auth_schema migration: 6 tables + tasks.user_id FK + tz=True ALTER (Wave 2)
- [x] 10-04-PLAN.md — PRAGMA listener + main.py cleanup + integration tests (Wave 3)

### Phase 11: Auth Core Modules + Services + DI
**Goal**: Pure-logic auth/key/rate-limit/CSRF modules and services exist with single-source-of-truth invariants and pass unit tests; not yet wired into any HTTP route.
**Depends on**: Phase 10
**Requirements**: AUTH-02, AUTH-08, AUTH-09, KEY-02, KEY-03, KEY-08, ANTI-03, VERIFY-05
**Success Criteria** (what must be TRUE):
  1. A unit test calling `app.core.password_hasher.hash(pw)` succeeds with Argon2id parameters `m=19456 KiB, t=2, p=1` and verifies the resulting hash round-trips
  2. A unit test calling `app.core.jwt_codec.decode_session()` rejects an `alg=none` token, a tampered token, and an expired token; grep proves `jwt.decode(` only appears inside `app/core/jwt_codec.py`
  3. A unit test calling `app.core.api_key.generate()` produces `whsk_<8>_<22>` strings of 36 chars total; `verify(plaintext, hash)` uses `secrets.compare_digest` and prefix lookup hits the `idx_api_keys_prefix` index
  4. `DI Container.password_service / token_service / auth_service / key_service / rate_limit_service / csrf_service` resolve to fresh instances; structured logs from these services contain no raw passwords, JWT secrets, or full API keys
  5. CI Argon2 benchmark asserts hash time stays under 300ms p99 on the deploy hardware profile
**Plans**: 5 plans (4 waves)
- [x] 11-01-PLAN.md — Foundation: argon2-cffi+pyjwt deps, AuthSettings, _sha256_hex helper, RedactingFilter wired, 9 typed auth exceptions (Wave 1)
- [x] 11-02-PLAN.md — 6 pure-logic core modules (password_hasher, jwt_codec, api_key, csrf, device_fingerprint, rate_limit) + 6 unit-test files (Wave 2)
- [ ] 11-03-PLAN.md — 4 domain entities + 4 repo Protocols + 4 mappers + 4 SQLAlchemy repos (idx_api_keys_prefix lookup, BEGIN IMMEDIATE upsert) (Wave 3)
- [ ] 11-04-PLAN.md — 6 services in app/services/auth/ + DI Container providers + 6 service unit-test files (Wave 4)
- [ ] 11-05-PLAN.md — Argon2 benchmark (p99<300ms slow gate) + DI smoke + log redaction integration tests (Wave 4)

### Phase 12: Admin CLI + Task Backfill
**Goal**: Operator can bootstrap an admin account and reassign all orphan `tasks` rows so the upcoming NOT-NULL FK constraint applies cleanly against the production database.
**Depends on**: Phase 11
**Requirements**: OPS-01, OPS-02, SCOPE-01
**Success Criteria** (what must be TRUE):
  1. Operator runs `python -m app.cli create-admin --email admin@example.com`, types the password at the `getpass` prompt, and a `users` row exists with Argon2id hash and `plan_tier='pro'`
  2. Operator runs `python -m app.cli backfill-tasks --admin-email admin@example.com` and every `tasks.user_id IS NULL` row is reassigned to the named admin (verifiable with `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL` returning 0)
  3. Subsequent migration tightens `tasks.user_id` to NOT NULL via `batch_alter_table` and adds `idx_tasks_user_id` index; migration succeeds against a copy of `records.db` without errors
  4. CLI never echoes the typed password to stdout, stderr, or any log destination
**Plans**: TBD

### Phase 13: Atomic Backend Cutover — **ATOMIC PAIR with Phase 14**
**Goal**: One backend deploy flips on dual-auth, per-user scoping, CSRF, CORS lockdown, rate limiting, free-tier gates, and Stripe-ready stubs — enforced everywhere on every endpoint.
**Depends on**: Phase 12
**Atomic Pair**: Phase 13 backend MUST deploy in lockstep with Phase 14 frontend. Half-shipping breaks the app — backend without frontend returns 401 to the existing SPA's anonymous fetches; frontend without backend lacks the routes the auth pages call. Build both on a branch, test end-to-end behind `AUTH_V2_ENABLED` flag, flip in a single release.
**Requirements**: AUTH-01, AUTH-03, AUTH-04, AUTH-05, AUTH-07, KEY-01, KEY-04, KEY-05, KEY-06, KEY-07, MID-01, MID-02, MID-03, MID-04, MID-05, MID-06, MID-07, SCOPE-02, SCOPE-03, SCOPE-04, SCOPE-05, RATE-01, RATE-02, RATE-03, RATE-04, RATE-05, RATE-06, RATE-07, RATE-08, RATE-09, RATE-10, RATE-11, RATE-12, ANTI-01, ANTI-02, ANTI-04, ANTI-05, ANTI-06, BILL-01, BILL-02, BILL-03, BILL-04, BILL-07
**Success Criteria** (what must be TRUE):
  1. New visitor `POST /auth/register` with valid email+password creates a user, sets the httpOnly+Secure+SameSite=Lax cookie session JWT, returns generic errors on duplicate (no enumeration); registered user `POST /auth/login` lands the same cookie and `POST /auth/logout` clears it; mailto link `hey@logingrupa.lv` is exposed for password reset
  2. Authenticated user `POST /api/keys` issues `whsk_<prefix>_<random>`, the full plaintext is returned exactly once in the response body; `GET /api/keys` lists name/prefix/created_at/last_used_at/status; `DELETE /api/keys/{id}` soft-deletes (revoked rows persist for audit); user can hold multiple active keys simultaneously
  3. Every request flows through `DualAuthMiddleware`: requests with `Authorization: Bearer whsk_*` set `request.state.auth_method='bearer'` and skip CSRF; cookie-authenticated state-mutating requests require matching `X-CSRF-Token` header (double-submit cookie); WebSocket connection requires a 60-second single-use ticket from `POST /api/ws/ticket` and rejects with HTTP 1008 when `ticket.user_id != task.user_id`; CORS is locked to explicit origin allowlist with `allow_credentials=true`
  4. User A authenticates and `GET /tasks`, `GET /task/{id}`, `DELETE /task/{id}`, `POST /speech-to-text*`, TUS upload, callback routes return only User A's data; User B is invisible across every endpoint; `DELETE /api/account/data` removes User A's tasks and uploaded files while preserving the user row
  5. Free-tier user hitting the 6th transcribe within an hour receives 429 with `Retry-After`; uploading >5min audio is rejected; only `tiny`/`small` models accept; trial countdown starts at first-key-creation; expired-trial transcribe returns 402; `POST /auth/register` from a single /24 returns 429 after 3/hr; `POST /auth/login` after 10/hr; disposable-email registrations are rejected; every completed transcription writes a `usage_events` row; user's `plan_tier` defaults to `trial` post-first-key, with nullable `stripe_customer_id` and `subscriptions` schema in place but unused at runtime
**Plans**: TBD

### Phase 14: Atomic Frontend Cutover + Test Infra — **ATOMIC PAIR with Phase 13**
**Goal**: Browser users land on a working auth shell — login/register/dashboard/keys/usage flows all functional, existing transcription UI preserved at `/`, all network calls flow through the central client; Vitest+RTL+MSW infrastructure verifies critical flows.
**Depends on**: Phase 13 (deploys atomically alongside)
**Atomic Pair**: See Phase 13. Backend cutover without this frontend means the existing SPA's raw fetches 401 instantly with no login page.
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-08, UI-09, UI-10, UI-11, UI-12, UI-13, TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06
**Success Criteria** (what must be TRUE):
  1. Anonymous visitor at `/ui` is redirected by `react-router-dom` BrowserRouter (basename `/ui`) to `/login`; submitting valid credentials lands them at `/` with the existing UploadDropzone+FileQueueList transcription UI intact at `routes/TranscribePage.tsx`; `?next=` is honored on redirect
  2. `/register` rejects weak passwords via the inline strength meter and zod schema; `/login` and `/register` use react-hook-form + shadcn `<Form>` styling, disable submit while loading, and redirect to `/` on success
  3. `/dashboard/keys` lists keys (name/prefix/created_at/last_used_at/status), the create-key modal shows the raw key exactly once with a working copy-to-clipboard, revoke prompts confirmation; `/dashboard/usage` displays current-hour quota counter, daily-minutes counter, and trial countdown badge
  4. Every API and WebSocket call flows through `frontend/src/lib/apiClient.ts` (auto-attaches credentials + `X-CSRF-Token`); 401 responses redirect to `/login?next=<currentUrl>`; 429 responses surface inline error with Retry-After countdown (no toast spam); `BroadcastChannel('auth')` propagates logout across browser tabs within one render cycle
  5. `bun run test` runs Vitest+jsdom with single `frontend/src/tests/setup.ts`, MSW handlers in `frontend/src/tests/msw/handlers.ts`, and the test suite passes for: apiClient 401 redirect, login form validation+happy path, register form validation, API key creation flow (show-once + copy), authStore login/logout, BroadcastChannel cross-tab sync, plus regression smoke for upload/transcribe/progress/export
**Plans**: TBD
**UI hint**: yes

### Phase 15: Account Dashboard Hardening + Billing Stubs
**Goal**: Polish the post-cutover account surface — full account deletion, logout-all-devices, Pro upgrade interest capture, and Stripe checkout/webhook stubs ready for v1.3 swap-in.
**Depends on**: Phase 14
**Requirements**: AUTH-06, SCOPE-06, UI-07, BILL-05, BILL-06
**Success Criteria** (what must be TRUE):
  1. User clicks "Logout all devices" on `/dashboard/account`, the `users.token_version` is bumped, every previously issued JWT for that user 401s on next request
  2. User completes the type-email confirmation flow on `/dashboard/account` and `DELETE /api/account` cascades the user row plus tasks, api_keys, subscriptions, usage_events
  3. `/dashboard/account` displays the user's email, plan_tier card, and "Upgrade to Pro" CTA which opens an interest-capture modal documenting v1.3 Stripe integration
  4. External client `POST /billing/checkout` returns `501 Not Implemented` with a placeholder body; `POST /billing/webhook` validates the `Stripe-Signature` header schema (rejects malformed) and returns `501 Not Implemented`
**Plans**: TBD
**UI hint**: yes

### Phase 16: Verification + Cross-User Matrix + E2E
**Goal**: Every critical security invariant is asserted by automated tests; the milestone is gated behind a green verification suite proving cross-user isolation, JWT hardening, CSRF enforcement, WS ticket safety, and migration correctness.
**Depends on**: Phase 15
**Requirements**: VERIFY-01, VERIFY-02, VERIFY-03, VERIFY-04, VERIFY-06, VERIFY-07, VERIFY-08
**Success Criteria** (what must be TRUE):
  1. Cross-user matrix test fixture seeds User A and User B; for every task-touching endpoint (`GET/DELETE /tasks`, `GET /task/{id}`, `POST /speech-to-text*`, TUS upload, WS, callbacks, `DELETE /api/account/data`), User B receives 404/403 attempting to access User A's resources — and vice versa
  2. JWT attack test asserts: `alg=none` token returns 401, tampered-signature token returns 401, expired token returns 401
  3. CSRF integration test asserts: cookie-auth state-mutating request without `X-CSRF-Token` header returns 403; with mismatched header returns 403; with matching header succeeds
  4. WebSocket ticket flow test asserts: ticket reuse returns 1008, expired ticket (>60s) returns 1008, ticket whose `user_id != task.user_id` returns 1008
  5. Migration smoke test runs against a copy of production `records.db`: baseline → upgrade → verify all `tasks.user_id` resolve to the seeded admin, all FK constraints enforce, no data loss
**Plans**: TBD

### Phase 17: Docs + Migration Runbook + Operator Guide
**Goal**: Operator and external API consumer have written guidance — migration runbook is followable end-to-end, `.env.example` lists every new variable with defaults, README documents the auth flow.
**Depends on**: Phase 16
**Requirements**: OPS-03, OPS-04, OPS-05
**Success Criteria** (what must be TRUE):
  1. Operator new to the project follows `docs/migration-v1.2.md` step-by-step (backup → `alembic stamp head` → `alembic upgrade head` → admin create → backfill → smoke verify) without consulting source code, and the migration completes successfully
  2. `.env.example` lists `JWT_SECRET`, `CSRF_SECRET`, `COOKIE_SECURE`, `COOKIE_DOMAIN`, `RATE_LIMIT_*`, `ARGON2_*`, `TRUST_CF_HEADER`, `FRONTEND_URL`, `HCAPTCHA_ENABLED`, `HCAPTCHA_SITE_KEY`, `HCAPTCHA_SECRET` with example values and inline comments
  3. `README.md` describes registration/login flow, API key issuance and bearer usage, free-vs-Pro tier differences, and the manual `mailto:hey@logingrupa.lv` password-reset path
**Plans**: TBD

### Phase 18: Stretch (Optional)
**Goal**: Optional additions that harden the auth surface without blocking the milestone — flip on if abuse observed during v1.2 soak.
**Depends on**: Phase 17 (optional, only if observed need warrants it)
**Requirements**: None (entirely deferred from FUTURE-* set; pulls forward only on demand)
**Success Criteria** (what must be TRUE):
  1. If hCaptcha activated: registration with invalid captcha token returns 403; with valid token succeeds
  2. If HaveIBeenPwned k-anonymity check enabled: registration with a top-1000 leaked password returns a generic error pointing the user to choose another
  3. If per-key scopes UI enabled: user can issue a key with `read-only` scope and a transcribe request with that key returns 403
  4. If per-key expiration enabled: expired key returns 401 even before user-driven revocation
**Plans**: TBD (gated on observed need; may close empty)

## Progress

**Execution Order:** 10 → 11 → 12 → 13+14 (atomic pair) → 15 → 16 → 17 → 18 (optional)

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 10. Alembic Baseline + Auth Schema | v1.2 | 4/4 | Complete    | 2026-04-29 |
| 11. Auth Core Modules + Services + DI | v1.2 | 2/5 | In Progress|  |
| 12. Admin CLI + Task Backfill | v1.2 | 0/TBD | Not started | - |
| 13. Atomic Backend Cutover | v1.2 | 0/TBD | Not started (atomic pair w/ 14) | - |
| 14. Atomic Frontend Cutover + Test Infra | v1.2 | 0/TBD | Not started (atomic pair w/ 13) | - |
| 15. Account Dashboard Hardening + Billing Stubs | v1.2 | 0/TBD | Not started | - |
| 16. Verification + Cross-User Matrix + E2E | v1.2 | 0/TBD | Not started | - |
| 17. Docs + Migration Runbook + Operator Guide | v1.2 | 0/TBD | Not started | - |
| 18. Stretch (Optional) | v1.2 | 0/TBD | Optional | - |

**Total Plans:** TBD (refined during plan-phase per phase)
**Requirements Coverage:** 95/95 mapped (v1.2 only)

---
*Roadmap created: 2026-01-29 (v1.0)*
*Updated: 2026-02-05 (v1.1 phase 9 plan)*
*Updated: 2026-04-29 (v1.2 milestone — 9 phases numbered 10-18; phases 13+14 atomic pair)*
