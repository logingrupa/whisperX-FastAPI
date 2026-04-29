# Requirements: WhisperX v1.2 Multi-User Auth + API Keys + Billing-Ready

**Defined:** 2026-04-29
**Core Value:** Users can sign up, get personal API keys, and use WhisperX via browser or external API with free-tier limits and Stripe-ready billing

---

## v1.1 Requirements (Reference — Shipped through Phase 9)

v1.1 chunked upload requirements live in milestone history. Phase 10 (Cloudflare integration, INTEG-01/02/03) deferred to v1.3.

| Status | Requirements |
|--------|--------------|
| Complete (v1.0) | All Phase 1-6 requirements (frontend foundation) |
| Complete (v1.1) | BACK-01..06 (Phase 7), FRONT-01..06 (Phase 8), RESIL-01..04 (Phase 9) |
| Deferred → v1.3 | INTEG-01, INTEG-02, INTEG-03 (Cloudflare proxy validation) |

---

## v1.2 Requirements

Requirements for multi-tenant SaaS auth retrofit. Numbering continues fresh per category.

### Schema and Migrations (`SCHEMA-*`)

- [x] **SCHEMA-01**: System uses Alembic migrations as the single source of truth for schema changes
- [x] **SCHEMA-02**: System has a baseline migration that mirrors the existing `tasks` table structure
- [x] **SCHEMA-03**: System adds `users`, `api_keys`, `subscriptions`, `usage_events`, `rate_limit_buckets`, `device_fingerprints` tables
- [x] **SCHEMA-04**: System adds `tasks.user_id` foreign key (nullable, then NOT NULL after backfill)
- [x] **SCHEMA-05**: System enforces SQLite `PRAGMA foreign_keys = ON` on every connection via SQLAlchemy event listener
- [x] **SCHEMA-06**: System uses `DateTime(timezone=True)` for every datetime column (prevents tz bugs at Stripe webhook time)
- [x] **SCHEMA-07**: `Subscription` table has `plan_tier` enum-CHECK constraint, `cancelled_at` soft-delete column, `stripe_customer_id` unique constraint
- [x] **SCHEMA-08**: `UsageEvent` table has `idempotency_key UNIQUE NOT NULL` for Stripe webhook replay safety

### Authentication Core (`AUTH-*`)

- [x] **AUTH-01**: User can register with email + password (single page, generic error messages — no enumeration)
- [x] **AUTH-02**: System hashes passwords with Argon2id using OWASP parameters (`m=19456 KiB, t=2, p=1`)
- [x] **AUTH-03**: User can log in with email + password and receive an httpOnly + Secure + SameSite=Lax cookie session JWT (HS256)
- [x] **AUTH-04**: Session is 7-day sliding-refresh (every authenticated request extends expiry)
- [x] **AUTH-05**: User can log out, clearing session cookie
- [x] **AUTH-06**: User can "logout all devices" via a `token_version` bump that invalidates every existing session
- [x] **AUTH-07**: User can request password reset by clicking a `mailto:hey@logingrupa.lv` link (no SMTP — manual operator response)
- [x] **AUTH-08**: All JWT decodes use `algorithms=["HS256"]` to prevent algorithm confusion (single decode site `app/core/jwt_codec.py`)
- [x] **AUTH-09**: System never logs raw passwords, JWT secrets, or full API keys at any log level

### API Keys (`KEY-*`)

- [x] **KEY-01**: Authenticated user can create named API keys via dashboard or API
- [x] **KEY-02**: System generates keys in format `whsk_<8charPrefix>_<22charBase64Random>` (16-byte url-safe base64, ~128 bits entropy)
- [x] **KEY-03**: System stores SHA-256 hash of API keys, never plaintext; uses `secrets.compare_digest` for verification
- [x] **KEY-04**: System shows the full API key exactly once at creation time (modal with copy-to-clipboard)
- [x] **KEY-05**: User can list their API keys with name, prefix, created_at, last_used_at, status (active/revoked)
- [x] **KEY-06**: User can have multiple active API keys simultaneously (no hard cap in v1.2)
- [x] **KEY-07**: User can revoke an API key; revoked keys are soft-deleted (kept indefinitely for audit until account deletion)
- [x] **KEY-08**: API key prefix lookup is indexed (no full-table scan on every bearer request)

### Dual-Auth Middleware (`MID-*`)

- [x] **MID-01**: System replaces existing `BearerAuthMiddleware` with `DualAuthMiddleware` accepting both cookie session JWT and `whsk_*` API key
- [x] **MID-02**: Middleware sets `request.state.user`, `request.state.plan_tier`, `request.state.auth_method`, `request.state.api_key_id`
- [x] **MID-03**: Middleware allowlists public paths: `/health`, `/health/live`, `/health/ready`, `/`, `/openapi.json`, `/docs`, `/redoc`, `/static`, `/favicon.ico`, `/auth/register`, `/auth/login`, `/ui/login`, `/ui/register`
- [x] **MID-04**: Bearer-authenticated routes skip CSRF verification automatically; cookie-authenticated state-mutating routes require `X-CSRF-Token` header (double-submit cookie pattern)
- [x] **MID-05**: System updates `tus_upload_api` to accept dual auth (API key for external clients, cookie+CSRF for browser)
- [x] **MID-06**: WebSocket endpoint requires a single-use 60-second ticket (issued via `POST /api/ws/ticket`, consumed via `?ticket=...` query param) — no subprotocol auth (Cloudflare strips)
- [x] **MID-07**: WebSocket handler rejects connection (HTTP 1008) if `ticket.user_id != task.user_id`

### Per-User Task Scoping (`SCOPE-*`)

- [x] **SCOPE-01**: `tasks.user_id` is NOT NULL after backfill migration; existing rows assigned to the bootstrap admin user
- [x] **SCOPE-02**: `ITaskRepository` exposes `set_user_scope(user_id)` that pushes the filter into the SQL `WHERE` clause for all reads and writes
- [x] **SCOPE-03**: `GET /tasks` returns only tasks owned by the authenticated user (cross-user matrix tests prove this for every endpoint)
- [x] **SCOPE-04**: `GET /task/{id}`, `DELETE /task/{id}`, `POST /speech-to-text*`, TUS upload routes, callback routes are all user-scoped
- [x] **SCOPE-05**: User can call `DELETE /api/account/data` to delete all their tasks and uploaded files; user row is preserved
- [x] **SCOPE-06**: User can call `DELETE /api/account` to delete their account entirely (cascades to tasks, api_keys, subscriptions, usage_events); type-email confirmation required at UI

### Rate Limiting and Free Tier (`RATE-*`)

- [x] **RATE-01**: System uses slowapi with a custom `key_func` that resolves `CF-Connecting-IP` (when `TRUST_CF_HEADER=true`), groups IPv4 by /24 and IPv6 by /64
- [x] **RATE-02**: System uses a SQLite-backed token bucket (`rate_limit_buckets`) with `BEGIN IMMEDIATE` for worker-safety
- [x] **RATE-03**: Free tier: 5 transcribe requests per hour per user
- [x] **RATE-04**: Free tier: maximum file duration 5 minutes
- [x] **RATE-05**: Free tier: maximum 30 minutes of audio processed per day
- [x] **RATE-06**: Free tier: only `tiny` and `small` models available; diarization disabled
- [x] **RATE-07**: Free tier: maximum 1 concurrent transcription
- [x] **RATE-08**: Free tier: 7-day trial counter starts at first API key creation (not registration)
- [x] **RATE-09**: Free tier: trial expiry returns `402 Payment Required` for transcription routes (auth still works)
- [x] **RATE-10**: Pro tier (€5/mo stub): 100 req/hr, file duration ≤60min, 600min/day audio cap, all models including `large-v3`, diarization enabled, 3 concurrent, queue priority
- [x] **RATE-11**: System writes a `usage_events` row for every completed transcription (user_id, task_id, gpu_seconds, file_seconds, model, idempotency_key)
- [x] **RATE-12**: 429 responses include `Retry-After` header in seconds; UI shows inline countdown

### Anti-Spam and Anti-DDOS (`ANTI-*`)

- [x] **ANTI-01**: `POST /auth/register` is throttled to 3 requests per hour per IP /24
- [x] **ANTI-02**: `POST /auth/login` is throttled to 10 requests per hour per IP /24
- [x] **ANTI-03**: System logs a `device_fingerprints` row at every login: cookie value hash, user-agent SHA-256, IP /24, `device_id` (UUID stored in browser localStorage)
- [x] **ANTI-04**: System rejects registration with disposable email domains (bundled blocklist, refreshed at boot)
- [x] **ANTI-05**: hCaptcha hook is scaffolded but feature-flagged off (`HCAPTCHA_ENABLED=false` default)
- [x] **ANTI-06**: CORS uses an explicit origin allowlist (`allow_origins=[FRONTEND_URL]`) with `allow_credentials=True` — never `["*"]` while cookies are issued

### Stripe-Ready Billing Schema (`BILL-*`)

- [x] **BILL-01**: User row has `plan_tier` enum (`free | trial | pro | team`) defaulting to `trial` after first key creation
- [x] **BILL-02**: User row has nullable `stripe_customer_id` (will be populated when Stripe goes live in v1.3)
- [x] **BILL-03**: `subscriptions` table is present with `stripe_subscription_id`, `plan`, `status`, `current_period_start`, `current_period_end`, `cancelled_at` (all nullable, populated by Stripe webhook in v1.3)
- [x] **BILL-04**: `usage_events` table is populated by every completed transcription (foundation for Stripe metered billing in v1.3)
- [x] **BILL-05**: `POST /billing/checkout` is a stub returning `501 Not Implemented` with a placeholder response (no live Stripe integration)
- [x] **BILL-06**: `POST /billing/webhook` is a stub that validates `Stripe-Signature` header schema (rejects malformed) and returns `501 Not Implemented`
- [x] **BILL-07**: System imports `stripe` package (15.1.0) but performs zero runtime API calls in v1.2

### Auth UI Pages (`UI-*`) — `/frontend-design` skill

- [x] **UI-01**: System uses `react-router-dom` with `<BrowserRouter basename="/ui">` and routes: `/`, `/login`, `/register`, `/dashboard/keys`, `/dashboard/usage`, `/dashboard/account`
- [x] **UI-02**: `/login` page has email + password fields with react-hook-form + zod validation, shadcn `<Form>` styling, submit-disabled-while-loading
- [x] **UI-03**: `/register` page has email + password + password-confirm + terms-checkbox, password strength meter (zxcvbn-style heuristic — no external library required)
- [x] **UI-04**: After successful login or registration, user is redirected to `/` (transcription page) or original `?next=` URL
- [x] **UI-05**: `/dashboard/keys` shows API key list (name, prefix, created_at, last_used_at, status), create-key modal that shows raw key once with copy button, revoke confirmation
- [x] **UI-06**: `/dashboard/usage` shows current-hour quota counter, daily minutes counter, trial countdown badge ("Trial: X days left" or "Trial not started" before first key)
- [x] **UI-07**: `/dashboard/account` shows email, plan_tier card, "Upgrade to Pro" CTA opening interest-capture modal (real Stripe in v1.3), delete-account flow with type-email confirmation
- [x] **UI-08**: 401 responses from `apiClient.ts` redirect to `/login?next=<currentUrl>`
- [x] **UI-09**: 429 responses surface inline error with `Retry-After` countdown — no toast spam
- [x] **UI-10**: Existing transcription page (`<UploadDropzone>`, `<FileQueueList>`, `<ConnectionStatus>`) is moved verbatim to `routes/TranscribePage.tsx` and rendered at `/`
- [x] **UI-11**: All API/WebSocket calls go through a single `frontend/src/lib/apiClient.ts` wrapper that auto-attaches credentials and `X-CSRF-Token`
- [x] **UI-12**: `BroadcastChannel('auth')` synchronizes login/logout state across browser tabs
- [x] **UI-13**: UI uses shadcn/ui + Tailwind v4 + Radix only — no custom components — and meets the "super pro modern" bar set via `/frontend-design` skill

### Frontend Test Infrastructure (`TEST-*`)

- [x] **TEST-01**: Project has Vitest 3.2 + jsdom configured with a single `frontend/src/tests/setup.ts`
- [x] **TEST-02**: Project has `@testing-library/react` 16.1, `@testing-library/user-event` 14.6, `@testing-library/jest-dom` 6.6 installed
- [x] **TEST-03**: Project has MSW 2.13 with handlers in `frontend/src/tests/msw/handlers.ts` and worker init in `frontend/public/`
- [x] **TEST-04**: Tests cover `apiClient.ts` 401 redirect, login form validation + happy path, register form validation, API key creation flow (show-once + copy), authStore login/logout actions, BroadcastChannel cross-tab sync
- [x] **TEST-05**: All async UI tests use `await user.click()` / `findByRole` to avoid React 19 + RTL 16 `act()` warnings
- [x] **TEST-06**: Existing functionality (upload, transcribe, progress, export) is regression-covered by smoke tests

### Operations and Tooling (`OPS-*`)

- [x] **OPS-01**: `python -m app.cli create-admin --email <e>` creates an admin user with hashed password (prompted via `getpass`, never stdin) and `plan_tier=pro`
- [x] **OPS-02**: `python -m app.cli backfill-tasks --admin-email <e>` assigns all `tasks.user_id IS NULL` rows to the named admin
- [ ] **OPS-03**: Migration runbook documented in `docs/migration-v1.2.md` (backup → `alembic stamp head` → `alembic upgrade head` → verify)
- [ ] **OPS-04**: `.env.example` lists every new env var with example values: `JWT_SECRET`, `CSRF_SECRET`, `COOKIE_SECURE`, `COOKIE_DOMAIN`, `RATE_LIMIT_*`, `ARGON2_*`, `TRUST_CF_HEADER`, `FRONTEND_URL`, `HCAPTCHA_ENABLED`, `HCAPTCHA_SITE_KEY`, `HCAPTCHA_SECRET`
- [ ] **OPS-05**: README.md documents the auth flow, key management, free vs Pro tiers, and the manual password-reset path

### Verification (`VERIFY-*`)

- [ ] **VERIFY-01**: Cross-user matrix tests prove that user A's tasks/keys/usage are never visible to user B for any endpoint
- [ ] **VERIFY-02**: JWT alg=none token is rejected with 401
- [ ] **VERIFY-03**: Tampered JWT signature is rejected with 401
- [ ] **VERIFY-04**: Expired JWT is rejected with 401
- [x] **VERIFY-05**: Argon2 hash benchmark stays under 300ms p99 on the deploy hardware (CI gate)
- [ ] **VERIFY-06**: CSRF token mismatch returns 403
- [ ] **VERIFY-07**: WebSocket ticket flow rejects re-use, expired tickets, and tickets bound to other users
- [ ] **VERIFY-08**: Migration smoke test runs against a copy of `records.db` end-to-end (baseline → upgrade → verify task ownership backfill correct)

## Future Requirements

Deferred to v1.3 or later.

- **FUTURE-01**: Real Stripe integration (Checkout, customer portal, webhook plan_tier flips)
- **FUTURE-02**: Single-GPU concurrency queue/worker with paid-tier priority (avoids VRAM OOM under burst)
- **FUTURE-03**: Cloudflare configuration + e2e validation (was v1.1 phase 10)
- **FUTURE-04**: SMTP integration (email verification at register, password reset email, magic link)
- **FUTURE-05**: TOTP 2FA / WebAuthn passkeys
- **FUTURE-06**: Per-API-key scopes UI (read-only / transcribe / admin)
- **FUTURE-07**: Per-API-key expiration date
- **FUTURE-08**: Active sessions list with per-session revoke
- **FUTURE-09**: Usage charts (daily/weekly/monthly) on `/dashboard/usage`
- **FUTURE-10**: HaveIBeenPwned password check (k-anonymity API)
- **FUTURE-11**: Refresh token rotation
- **FUTURE-12**: Email change flow

## Out of Scope

Explicitly excluded from v1.2.

| Feature | Reason |
|---------|--------|
| Mobile app | Web-first, desktop/tablet focus |
| Real-time streaming transcription | Batch processing only |
| Audio editing | Transcription only, not an editor |
| Inline transcript editing | Complex state management, export to editor instead |
| Video player with transcript sync | HTML5 video complexity |
| Team plans / shared workspaces | Single-user accounts only in v1.2 |
| Username field at registration | Email is the only identifier |
| Required phone number at registration | Friction without value at this stage |
| localStorage JWT storage | XSS risk; cookie session is mandatory |
| Custom payment form | Stripe Checkout redirect pattern only |
| Forced password rotation | NIST SP 800-63 advises against periodic rotation |
| Security questions | Phishing-prone, low entropy |
| GET endpoints that mutate state | Lint-enforced: `@router.get` is read-only |

## Traceability

Phase mapping established by `/gsd-roadmap` 2026-04-29. Every v1.2 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCHEMA-01 | Phase 10 | Complete |
| SCHEMA-02 | Phase 10 | Complete |
| SCHEMA-03 | Phase 10 | Complete |
| SCHEMA-04 | Phase 10 | Complete |
| SCHEMA-05 | Phase 10 | Complete |
| SCHEMA-06 | Phase 10 | Complete |
| SCHEMA-07 | Phase 10 | Complete |
| SCHEMA-08 | Phase 10 | Complete |
| AUTH-01 | Phase 13 | Complete |
| AUTH-02 | Phase 11 | Complete |
| AUTH-03 | Phase 13 | Complete |
| AUTH-04 | Phase 13 | Complete |
| AUTH-05 | Phase 13 | Complete |
| AUTH-06 | Phase 15 | Complete |
| AUTH-07 | Phase 13 | Complete |
| AUTH-08 | Phase 11 | Complete |
| AUTH-09 | Phase 11 | Complete |
| KEY-01 | Phase 13 | Complete |
| KEY-02 | Phase 11 | Complete |
| KEY-03 | Phase 11 | Complete |
| KEY-04 | Phase 13 | Complete |
| KEY-05 | Phase 13 | Complete |
| KEY-06 | Phase 13 | Complete |
| KEY-07 | Phase 13 | Complete |
| KEY-08 | Phase 11 | Complete |
| MID-01 | Phase 13 | Complete |
| MID-02 | Phase 13 | Complete |
| MID-03 | Phase 13 | Complete |
| MID-04 | Phase 13 | Complete |
| MID-05 | Phase 13 | Complete |
| MID-06 | Phase 13 | Complete |
| MID-07 | Phase 13 | Complete |
| SCOPE-01 | Phase 12 | Complete |
| SCOPE-02 | Phase 13 | Complete |
| SCOPE-03 | Phase 13 | Complete |
| SCOPE-04 | Phase 13 | Complete |
| SCOPE-05 | Phase 13 | Complete |
| SCOPE-06 | Phase 15 | Complete |
| RATE-01 | Phase 13 | Complete |
| RATE-02 | Phase 13 | Complete |
| RATE-03 | Phase 13 | Complete |
| RATE-04 | Phase 13 | Complete |
| RATE-05 | Phase 13 | Complete |
| RATE-06 | Phase 13 | Complete |
| RATE-07 | Phase 13 | Complete |
| RATE-08 | Phase 13 | Complete |
| RATE-09 | Phase 13 | Complete |
| RATE-10 | Phase 13 | Complete |
| RATE-11 | Phase 13 | Complete |
| RATE-12 | Phase 13 | Complete |
| ANTI-01 | Phase 13 | Complete |
| ANTI-02 | Phase 13 | Complete |
| ANTI-03 | Phase 11 | Complete |
| ANTI-04 | Phase 13 | Complete |
| ANTI-05 | Phase 13 | Complete |
| ANTI-06 | Phase 13 | Complete |
| BILL-01 | Phase 13 | Complete |
| BILL-02 | Phase 13 | Complete |
| BILL-03 | Phase 13 | Complete |
| BILL-04 | Phase 13 | Complete |
| BILL-05 | Phase 15 | Complete |
| BILL-06 | Phase 15 | Complete |
| BILL-07 | Phase 13 | Complete |
| UI-01 | Phase 14 | Complete |
| UI-02 | Phase 14 | Complete |
| UI-03 | Phase 14 | Complete |
| UI-04 | Phase 14 | Complete |
| UI-05 | Phase 14 | Complete |
| UI-06 | Phase 14 | Complete |
| UI-07 | Phase 15 | Complete |
| UI-08 | Phase 14 | Complete |
| UI-09 | Phase 14 | Complete |
| UI-10 | Phase 14 | Complete |
| UI-11 | Phase 14 | Complete |
| UI-12 | Phase 14 | Complete |
| UI-13 | Phase 14 | Complete |
| TEST-01 | Phase 14 | Complete |
| TEST-02 | Phase 14 | Complete |
| TEST-03 | Phase 14 | Complete |
| TEST-04 | Phase 14 | Complete |
| TEST-05 | Phase 14 | Complete |
| TEST-06 | Phase 14 | Complete |
| OPS-01 | Phase 12 | Complete |
| OPS-02 | Phase 12 | Complete |
| OPS-03 | Phase 17 | Pending |
| OPS-04 | Phase 17 | Pending |
| OPS-05 | Phase 17 | Pending |
| VERIFY-01 | Phase 16 | Pending |
| VERIFY-02 | Phase 16 | Pending |
| VERIFY-03 | Phase 16 | Pending |
| VERIFY-04 | Phase 16 | Pending |
| VERIFY-05 | Phase 11 | Complete |
| VERIFY-06 | Phase 16 | Pending |
| VERIFY-07 | Phase 16 | Pending |
| VERIFY-08 | Phase 16 | Pending |

**Coverage:**
- v1.2 requirements: 95 total (corrected from earlier "84" header — actual category counts: SCHEMA 8 + AUTH 9 + KEY 8 + MID 7 + SCOPE 6 + RATE 12 + ANTI 6 + BILL 7 + UI 13 + TEST 6 + OPS 5 + VERIFY 8 = 95)
- Mapped to phases: 95 (100%)
- Unmapped: 0

**Phase distribution:**
- Phase 10 (Alembic Baseline + Auth Schema): 8
- Phase 11 (Auth Core Modules + Services + DI): 8
- Phase 12 (Admin CLI + Task Backfill): 3
- Phase 13 (Atomic Backend Cutover): 43
- Phase 14 (Atomic Frontend Cutover + Test Infra): 18
- Phase 15 (Account Dashboard Hardening + Billing Stubs): 5
- Phase 16 (Verification + Cross-User Matrix + E2E): 7
- Phase 17 (Docs + Migration Runbook): 3
- Phase 18 (Stretch — optional): 0

---
*v1.2 requirements defined: 2026-04-29*
*Last updated: 2026-04-29 — phase mapping completed by gsd-roadmapper (95 reqs → phases 10-18)*
