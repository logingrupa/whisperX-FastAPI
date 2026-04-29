# Phase 13: Atomic Backend Cutover - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning
**Mode:** Auto-generated (decisions locked in STATE.md/REQUIREMENTS.md from milestone discuss)
**Atomic Pair:** Phase 13 backend MUST deploy in lockstep with Phase 14 frontend.

<domain>
## Phase Boundary

One backend deploy flips on dual-auth, per-user scoping, CSRF, CORS lockdown, rate limiting, free-tier gates, and Stripe-ready stubs — enforced everywhere on every endpoint. Built behind `AUTH_V2_ENABLED` feature flag so the half-deployed state never reaches users.

In scope:
- HTTP routes (`/auth/register`, `/auth/login`, `/auth/logout`, `/api/keys`, `/api/keys/{id}`, `/api/account/data`, `/api/ws/ticket`, `/billing/checkout` (501), `/billing/webhook` (501))
- `DualAuthMiddleware` replacing `BearerAuthMiddleware` — cookie JWT OR `whsk_*` bearer
- CSRF double-submit middleware enforcement
- Per-user scoping on EVERY endpoint touching `tasks` (`GET /tasks`, `GET /task/{id}`, `DELETE /task/{id}`, `POST /speech-to-text*`, TUS upload, callback)
- WebSocket ticket flow (`POST /api/ws/ticket` issues 60s single-use; WS endpoint validates and rejects HTTP 1008 on user mismatch)
- Rate limiting via slowapi + custom `key_func` (CF-Connecting-IP /24/64) + SQLite-backed token bucket from Phase 11
- Free-tier policies: 5 req/hr, ≤5min file, ≤30min/day, tiny/small only, 1 concurrent, back-of-queue
- Trial countdown: starts at first-key-created; expired returns 402 on transcribe routes (auth still works)
- Anti-spam: register 3/hr per /24; login 10/hr per /24; disposable-email blocklist; hCaptcha hook scaffolded but feature-flagged off
- CORS lockdown: explicit `allow_origins=[FRONTEND_URL]` + `allow_credentials=True`
- Stripe stubs: `POST /billing/checkout` and `POST /billing/webhook` return 501; `stripe` package imported but no runtime calls; `plan_tier` defaults to `trial` after first key creation
- `DELETE /api/account/data` — deletes tasks + uploaded files, keeps user row
- Per-completed-transcription `usage_events` row write
- Logout-all-devices via `token_version` bump (AUTH-06 polish moved to Phase 15)
- Feature flag `AUTH_V2_ENABLED` gates the entire surface — defaults `false` in dev, set `true` in deploy

Out of scope (explicit deferrals to Phase 14/15/16/17/18):
- Frontend auth shell, react-router, login/register pages, dashboard — Phase 14
- AUTH-06 logout-all-devices UI button — Phase 15
- SCOPE-06 DELETE /api/account (full account deletion) — Phase 15
- BILL-05/06 checkout/webhook UI — Phase 15 (this phase ships them as 501 stubs only)
- Cross-user matrix tests + JWT attack matrix + WS ticket reuse tests — Phase 16
- Migration runbook + .env.example documentation — Phase 17
- Real Stripe integration — v1.3 (FUTURE-01)

</domain>

<decisions>
## Implementation Decisions

(All locked from STATE.md "v1.2 entry decisions" + REQUIREMENTS.md.)

### DualAuthMiddleware (replaces BearerAuthMiddleware)

- File: `app/core/dual_auth.py` (new); replaces `app/core/auth.py` (delete after wiring; DON'T leave dead code)
- Resolution order on each request:
  1. `Authorization: Bearer whsk_*` → `auth_method='bearer'`; resolve via `KeyService.verify_plaintext(plain)`; sets `request.state.user`, `request.state.api_key_id`, `request.state.plan_tier`
  2. Else cookie `session=<jwt>` → `auth_method='cookie'`; verify via `TokenService.verify_and_refresh()`; sets `request.state.user`, `request.state.plan_tier`
  3. Else if path is in PUBLIC_ALLOWLIST → pass through; `request.state.user = None`, `request.state.plan_tier = None`
  4. Else → 401 JSON `{"detail": "Authentication required"}`
- PUBLIC_ALLOWLIST (locked from MID-03): `/health`, `/health/live`, `/health/ready`, `/`, `/openapi.json`, `/docs`, `/redoc`, `/static`, `/favicon.ico`, `/auth/register`, `/auth/login`, `/ui/login`, `/ui/register`
- Cookie-auth state-mutating routes (POST/PUT/PATCH/DELETE) require `X-CSRF-Token` header matching `csrf_token` cookie (double-submit, `secrets.compare_digest`); bearer-auth routes skip CSRF
- WebSocket route is exempted from middleware response wrapping (still uses ticket flow)

### Cookie Session Policy

- Cookie name: `session`
- Attributes: `httpOnly=True`, `secure=True` (gated on `COOKIE_SECURE=true` in non-test envs), `samesite=lax`, `max_age=7*24*3600`, `path="/"`, `domain=COOKIE_DOMAIN` (env var, default empty)
- On every authenticated request the middleware re-issues the cookie with refreshed `exp` (sliding 7-day window — AUTH-04)
- Logout → set cookie `Max-Age=0` to clear

### CSRF Cookie

- Cookie name: `csrf_token`
- Attributes: `httpOnly=False` (frontend reads it to send X-CSRF-Token header), `secure=True` (prod), `samesite=lax`, `max_age=session-life`, `path="/"`
- Set on login, register, ticket-issue
- Verified by middleware on cookie-auth state-mutating routes only

### Auth Routes (`app/api/auth_routes.py`)

- `POST /auth/register` — body `{email, password}`; rate-limited 3/hr/IP/24; returns 201 with cookie set; generic error on duplicate (no enumeration: `"Registration failed"`)
- `POST /auth/login` — body `{email, password}`; rate-limited 10/hr/IP/24; returns 200 with cookie set; generic error `"Invalid credentials"` on either wrong-email or wrong-password
- `POST /auth/logout` — clears `session` and `csrf_token` cookies; returns 204; idempotent (no-op if no session)
- Mailto password reset surfaced as a static link in the OpenAPI description: `mailto:hey@logingrupa.lv` (no endpoint — operator handles manually per AUTH-07)

### Key Routes (`app/api/key_routes.py`)

- `POST /api/keys` — body `{name: str}`; auth required (cookie OR bearer); response `{id, prefix, key, name, created_at, status}` — `key` shown ONCE, never again
- `GET /api/keys` — auth required; returns list of `{id, name, prefix, created_at, last_used_at, status}` (no plaintext)
- `DELETE /api/keys/{id}` — auth required; soft-delete (sets `revoked_at = now`); returns 204; revoked rows persist for audit
- Multiple active keys per user — no cap (KEY-06)

### Account Routes (`app/api/account_routes.py`)

- `DELETE /api/account/data` — auth required (cookie OR bearer); deletes user's tasks AND uploaded files (cascade via FK); preserves user row; returns 204
- Note: `DELETE /api/account` (full row deletion) deferred to Phase 15

### WebSocket Ticket Flow

- `POST /api/ws/ticket` — auth required; body `{task_id: int}`; verifies `task.user_id == auth_user.id`; returns `{ticket: <random 32 chars>, expires_at: <60s>}`; persists in-memory or in-DB (decision: in-memory dict with TTL eviction per worker; for v1.2 single-worker is fine)
- WebSocket endpoint accepts `?ticket=<token>` query param; consumes ticket (single-use); rejects with `code=1008` (Policy Violation) if expired/reused/missing OR `ticket.user_id != task.user_id`

### Per-User Scoping

- `ITaskRepository` adds `set_user_scope(user_id: int)` — pushes `WHERE user_id = :user_id` filter into all read/write queries (locked SCOPE-02)
- Every existing endpoint that hits `tasks` adds `Depends(get_scoped_task_repository)` which calls `set_user_scope(request.state.user.id)` before yielding
- This includes: `GET /tasks`, `GET /task/{id}`, `DELETE /task/{id}`, `POST /speech-to-text` family, TUS upload routes, callback routes
- Cross-user requests return 404 (not 403) — opaque (no enumeration of other users' tasks)

### Rate Limiting

- Library: slowapi (already standard with FastAPI); add to deps
- Storage backend: SQLite-backed token bucket via `RateLimitService` from Phase 11 (no external Redis)
- `key_func`: resolves `CF-Connecting-IP` (when `TRUST_CF_HEADER=true` env), groups IPv4 by /24, IPv6 by /64
- Free-tier policies (RATE-03 through RATE-08):
  - 5 transcribe/hr per user (`user:{id}:tx:hour`)
  - ≤5min file duration (validated at upload start; longer rejected with 413/422)
  - ≤30min/day audio cumulative (`user:{id}:audio_min:day`)
  - Models: `tiny` and `small` only (other models rejected with 403 + clear message)
  - Diarization: disabled
  - 1 concurrent transcription (`user:{id}:concurrent` semaphore)
- Pro tier (€5/mo stub): 100/hr, ≤60min file, ≤600min/day, all models incl. large-v3, diarization on, 3 concurrent, queue priority
- Trial: starts at first-key-created (sets `users.trial_started_at = now`); 7-day window; expired → 402 on transcribe routes only (auth still works)
- 429 responses include `Retry-After: <seconds>` header
- Anti-DDOS: register `3/hr/ip:/24`; login `10/hr/ip:/24` (separate buckets, applied as slowapi decorators on those routes)

### Anti-Spam

- Disposable-email blocklist: `data/disposable-emails.txt` bundled at repo (small list ~3000 domains); refreshed at boot via module-load read into a `frozenset`
- Registration rejects emails matching the blocklist with generic 422 `"Registration failed"` (no enumeration)
- hCaptcha hook: scaffold middleware that checks `H-Captcha-Response` header on `/auth/register` and `/auth/login` if `HCAPTCHA_ENABLED=true`; default off

### CORS

- Library: starlette CORSMiddleware (already in app/main.py)
- `allow_origins`: explicit list from `FRONTEND_URL` env (single origin for v1.2; comma-split if multiple)
- `allow_credentials=True`
- `allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
- `allow_headers=["*"]` for v1.2 simplicity (tighten in v1.3)
- NEVER `allow_origins=["*"]` — incompatible with cookies (ANTI-06)

### Free-Tier Gates (RATE-03..RATE-09)

- Implemented in service-layer middleware: a `FreeTierGate` dependency injected into every transcription route
- On every transcribe call, checks (in order, fail-fast):
  1. `RateLimitService.consume(user_id, "tx", 1, hour=5)` — else 429 with `Retry-After`
  2. Trial expiry — if `trial_started_at + 7d < now` → 402
  3. File duration ≤5min — else 422
  4. Daily audio cap — `RateLimitService.consume(user_id, "audio_min", duration_min, day=30)` — else 429
  5. Model in `{tiny, small}` (free) or `{tiny, small, base, medium, large-v3}` (pro) — else 403
  6. Concurrency slot acquired — else 429

### Usage Events (RATE-11, BILL-04)

- Every completed transcription writes a `usage_events` row: `(user_id, task_id, gpu_seconds, file_seconds, model, idempotency_key=task.uuid, created_at)`
- `idempotency_key` UNIQUE NOT NULL — duplicate writes (re-enqueue scenarios) caught by constraint
- Hook lives in the existing `task_management_service.complete_task` flow

### Stripe Stubs

- `POST /billing/checkout` — auth required; returns 501 `{"detail": "Not Implemented", "status": "stub", "hint": "Stripe integration arrives in v1.3"}`
- `POST /billing/webhook` — validates `Stripe-Signature` header **schema** (rejects malformed); returns 501 with same shape
- Import `stripe` at module load (BILL-07) — verify with `import stripe` at startup; never call `stripe.*` at runtime in v1.2

### Feature Flag `AUTH_V2_ENABLED`

- Env var `AUTH_V2_ENABLED` (default `false`); read into `Settings.auth.V2_ENABLED`
- When `false`: legacy `BearerAuthMiddleware` is wired; `/auth/*`, `/api/keys/*`, `/api/account/data`, etc. routes are NOT registered (or all return 503)
- When `true`: `DualAuthMiddleware` is wired; all new routes active; `BearerAuthMiddleware` is removed
- The flip from `false → true` is the atomic deploy moment (paired with Phase 14)

### Code Quality (locked from user)

- **DRY** — Shared `Depends(get_authenticated_user)` and `Depends(get_scoped_task_repository)` across all routes; never duplicate auth resolution
- **SRP** — Routes do HTTP concerns; services do business logic; repos do persistence; middleware does auth only
- **/tiger-style** — feature flag default OFF; assert at app boot that JWT_SECRET ≠ dev-only when `ENVIRONMENT=production` AND `AUTH_V2_ENABLED=true` (production safety check); fail loudly on missing AUTH__JWT_SECRET in prod
- **No spaghetti / no nested-if-in-if-in-if** — `grep -cE "^\s+if .*\bif\b" app/api/*.py app/core/*.py` returns 0
- **Self-explanatory names** — `get_authenticated_user`, `get_scoped_task_repository`, `DualAuthMiddleware`, `FreeTierGate`, `RateLimitService`, no abbreviations

### Claude's Discretion

- Exact file split: `app/api/auth_routes.py`, `app/api/key_routes.py`, `app/api/account_routes.py`, `app/api/billing_routes.py`, `app/api/dependencies.py` (extend existing); `app/core/dual_auth.py`, `app/core/csrf_middleware.py`, `app/core/feature_flags.py`
- Cookie domain default: empty (lets browser default to request host)
- Per-route slowapi decorator vs middleware-level: per-route for register/login (clearer); middleware-level via dependency for free-tier transcribe gates

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/core/container.py` — already has `auth_service`, `key_service`, `token_service`, `csrf_service`, `password_service`, `rate_limit_service` providers (Phase 11)
- `app/services/auth/*` — register_user, login, verify_and_refresh, create_key, verify_plaintext, etc. — call from routes
- `app/api/dependencies.py` — extend with `get_authenticated_user`, `get_scoped_task_repository`, `get_csrf_context`, `get_rate_limit_service`
- `app/core/csrf.py` — pure-logic CSRF (Phase 11) — wrap with middleware
- `app/core/jwt_codec.py` — single jwt site (Phase 11)
- `app/core/api_key.py` — whsk_ format (Phase 11)
- `app/core/auth.py` — legacy BearerAuthMiddleware — DELETE after wiring DualAuthMiddleware
- `app/main.py` — `app.add_middleware(BearerAuthMiddleware)` line — replace
- `app/main.py` — `app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)` — replace with explicit allowlist

### Established Patterns

- FastAPI `APIRouter` per concern (e.g. `stt_router`, `task_router`, `service_router`)
- `Depends()` for DI; `request.state` for middleware-set context
- Pydantic v2 schemas in `app/api/schemas/` and `app/schemas.py`
- Exception handlers in `app/api/exception_handlers.py` — register new typed exceptions there
- Pytest markers: unit / integration / e2e

### Integration Points

- `app/main.py` — middleware stack: `app.add_middleware(DualAuthMiddleware)` (replaces BearerAuthMiddleware); `CORSMiddleware` config replaced
- `app/main.py` — `app.include_router(auth_router); app.include_router(key_router); app.include_router(account_router); app.include_router(billing_router)`
- `app/api/dependencies.py` — extend
- `app/api/exception_handlers.py` — register handlers for `InvalidCredentialsError`, `UserAlreadyExistsError`, `RateLimitExceededError`, `WeakPasswordError`, `InvalidApiKeyFormatError`, `JwtAlgorithmError`/`JwtExpiredError`/`JwtTamperedError`, `CsrfMismatchError`
- `app/api/tus_upload_api.py` — add scoping
- `app/api/audio_api.py` — add scoping + free-tier gate
- `app/api/task_api.py` — add scoping
- `app/api/audio_services_api.py` — add scoping + free-tier gate
- `app/api/callbacks.py` — add scoping (for callback URLs only firing for the user's own tasks)
- `app/api/websocket_api.py` (or wherever WS endpoint lives) — add ticket validation
- `pyproject.toml` — add `slowapi`, `stripe` (15.1.0)

</code_context>

<specifics>
## Specific Ideas

- Build behind `AUTH_V2_ENABLED` so dev environment can keep using the old BearerAuthMiddleware until paired Phase 14 frontend is ready
- Phase 16 will run cross-user matrix tests + JWT attack tests + WS ticket-reuse tests — keep test hooks easy to mount
- Disposable email blocklist file: bundle as `data/disposable-emails.txt`; loader reads at module load into `frozenset` (O(1) lookup)
- Free-tier gate is a `Depends()` — order matters: rate-check first (fast), then trial-check, then file-validation, then concurrency slot acquisition (last, since releasing on failure is awkward)
- `usage_events` write is idempotent via `idempotency_key=task.uuid` — replays won't double-bill in v1.3 Stripe metered billing

</specifics>

<deferred>
## Deferred Ideas

- Cross-user matrix tests, JWT attack tests, WS reuse tests — Phase 16
- AUTH-06 logout-all-devices, SCOPE-06 full account delete, BILL-05/06 UI, UI-07 account dashboard polish — Phase 15
- Migration runbook + `.env.example` updates + README docs — Phase 17
- Real Stripe integration — v1.3
- SMTP password reset — v1.3
- TOTP / WebAuthn — v1.3+
- Refresh token rotation — v1.3+

</deferred>
