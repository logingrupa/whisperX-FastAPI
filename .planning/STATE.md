---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: milestone
status: executing
stopped_at: Plan 14-01 complete — Vitest+jsdom+RTL+MSW infra online; shadcn primitives + zustand/RHF/zod deps installed; sentinel 2/2; 2 commits (b0de895, dff607a)
last_updated: "2026-04-29T13:27:38.385Z"
last_activity: 2026-04-29
progress:
  total_phases: 9
  completed_phases: 4
  total_plans: 30
  completed_plans: 25
  percent: 83
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-29)

**Core value:** Users can sign up, get API keys, and use WhisperX via browser or external API with free-tier limits and Stripe-ready billing
**Current focus:** Phase 14 — Atomic Frontend Cutover + Test Infra

## Current Position

Phase: 14 (Atomic Frontend Cutover + Test Infra) — EXECUTING
Plan: 3 of 7
Status: Ready to execute
Last activity: 2026-04-29

## Performance Metrics

**Velocity (v1.1 final):**

- Total plans completed: 31 (v1.1)
- Average duration: 2.9 min
- Total execution time: 0.39 hours

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 7 | 3/3 | 10m | 3.3m |
| 8 | 3/4 | 7m | 2.3m |
| 9 | 2/3 | 7m | 3.5m |
| 10 | 4 | - | - |
| 11 | 5 | - | - |
| 12 | 4 | - | - |
| 13 | 10 | - | - |

*Reset on each plan completion in v1.2.*
| Phase 10 P01 | 5min | 3 tasks | 6 files |
| Phase 10 P02 | 3min | 2 tasks | 2 files |
| Phase 10 P03 | 2min | 1 tasks | 1 files |
| Phase 10 P04 | 9 | 3 tasks | 2 files |
| Phase 11 P01 | 6 | 2 tasks | 6 files |
| Phase 11 P02 | 9m | 2 tasks | 12 files |
| Phase 11 P03 | 5m | 2 tasks | 16 files |
| Phase 11 P04 | 11m | 2 tasks | 15 files |
| Phase 11 P05 | 5m | 1 tasks | 3 files |
| Phase 12 P01 | 6 min | 1 tasks | 9 files |
| Phase 12 P02 | 5 min | 1 tasks (TDD) | 3 files |
| Phase 12 P03 | 3 | 1 tasks | 2 files |
| Phase 12 P04 | 90 min | 2 tasks tasks | 3 files files |
| Phase 13 P01 | 3m 39s | 3 tasks | 4 files |
| Phase 13 P02 | 6m | 2 tasks | 5 files |
| Phase 13 P03 | ~17m | 3 tasks | 7 files |
| Phase 13 P04 | 4 min | - tasks | - files |
| Phase 13 P05 | 10 min | 3 tasks | 8 files |
| Phase 13 P06 | 25 min | 3 tasks | 10 files |
| Phase 13 P07 | 10 min | 3 tasks | 11 files |
| Phase 13 P08 | 20 min | 3 tasks | 15 files |
| Phase 13 P08 | 20 min | 3 tasks | 15 files |
| Phase 13 P09 | 10 min | 3 tasks | 3 files |
| Phase 13 P10 | 26 min | 1 tasks | 5 files |
| Phase 14 P01 | 3m 30s | 2 tasks | 16 files |
| Phase 14 P02 | 2m 28s | 2 tasks | 5 files |

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
- Argon2 password hashing (OWASP `m=19456 KiB, t=2, p=1`)
- Trial counter starts at first-key-created (not registration)
- Free tier: 5 req/hr + file <5min + 30min/day + tiny/small models only + 1 concurrent slot + back-of-queue
- Anti-DDOS: 3 register/hr per IP/24, 10 login/hr per IP/24
- Device fingerprint = cookie + ua hash + ip /24 + device_id (localStorage uuid)
- mailto password reset → `hey@logingrupa.lv` (no SMTP)
- Many API keys per user (named, scopes-ready, hashed sha256)
- Self-serve `DELETE /api/account/data` (tasks + files, keeps user row)
- Stripe stub now: `Subscription`, `UsageEvent`, `plan_tier` enum, €5/mo "Pro" placeholder
- Tasks gain `user_id` FK; existing rows backfilled to admin user
- Alembic migrations introduced; baseline existing schema
- react-router-dom (already in deps) for `/login`, `/register`, `/dashboard/*` routes
- Vitest + React Testing Library + MSW for frontend test infra
- `/frontend-design` skill for all auth UI pages (super pro modern UI)
- Caveman mode passed to all subagents (token savings)

v1.2 roadmap decisions (locked 2026-04-29 by gsd-roadmapper):

- 9 phases numbered 10-18 (resume from v1.1 phase 9; v1.1 phase 10 Cloudflare deferred to v1.3)
- Phases 13 + 14 are an **atomic pair** — single deploy; build behind `AUTH_V2_ENABLED` flag, flip together
- Phase 10-12 ship as silent infra (no behavior change to end users)
- Phase 15 absorbs polish-tier UI/auth: AUTH-06 logout-all-devices, SCOPE-06 delete-account, UI-07 account dashboard, BILL-05/06 checkout/webhook 501 stubs (post-cutover safe)
- Phase 16 is gate-to-milestone-close (cross-user matrix + JWT attack tests + WS ticket reuse + migration smoke)
- Phase 18 stretch is explicitly optional, no v1.2 reqs (FUTURE-* set; pulled forward only on observed need)
- Coverage: 95 v1.2 reqs mapped 100% (REQUIREMENTS.md header "84" was stale; actual category sum = 95)
- [Phase ?]: [10-01]: Alembic 1.17.0 baseline; env.py wired to Config.DB_URL (single source of truth); 0001_baseline mirrors current ORM Task verbatim (19 cols)
- [Phase ?]: [10-02]: ORM-level tz-awareness for Task migrated proactively in Plan 02 (factory swap), not Plan 03 batch_alter_table — single source of truth, Plan 03 mirrors ORM mechanically
- [Phase ?]: [10-02]: relationship() not imported anywhere (DRT — back-population deferred to Phase 11 repository layer; zero unused symbols)
- [Phase ?]: [10-02]: DRY factory invocation table locked at 6 created_at + 3 updated_at = 9 — RateLimitBucket uses inline last_refill (semantic-different), Task gets factory swap to match new tz-aware DB shape
- [Phase ?]: [10-03]: Single-line op.create_table opener form mandated by plan grep gates — same Plan-10-01-style fix applied
- [Phase ?]: [10-03]: 14 named constraints in 0002_auth_schema (6 FK + 1 CK + 1 IX + 6 UQ); usage_events.task_id FK lacks ondelete=CASCADE (audit trail per CONTEXT §38)
- [Phase ?]: [10-03]: Greenfield smoke verified end-to-end: alembic upgrade head creates 8 tables; ck_users_plan_tier rejects invalid; uq_usage_events_idempotency_key rejects duplicate; downgrade -1 returns to baseline shape
- [Phase ?]: [10-04]: SQLAlchemy global Engine 'connect' listener for PRAGMA foreign_keys=ON; module-load fail-loud assert refuses to boot if FK enforcement off
- [Phase ?]: [10-04]: Base.metadata.create_all removed from app/main.py — Alembic is the sole schema source; partial-staged via git apply --cached to isolate from pre-existing dirty BearerAuthMiddleware diff
- [Phase ?]: [10-04]: subprocess invocation uses [sys.executable, '-m', 'alembic', ...] — venv-portable, PATH-independent, fixes Windows pytest test discovery
- [Phase ?]: [10-04]: Phase 10 schema-foundation milestone closed — SCHEMA-01..08 all delivered across plans 10-01..10-04
- [Phase ?]: [11-01]: AuthSettings env_prefix=AUTH__ explicitly set on model_config — required for default_factory-constructed nested settings to honor AUTH__JWT_SECRET / AUTH__CSRF_SECRET env vars
- [Phase ?]: [11-01]: Production-safety model_validator on AuthSettings — refuses to boot when ENVIRONMENT=production AND JWT_SECRET/CSRF_SECRET are dev defaults; threat T-11-02 mitigated in this phase rather than deferred to Phase 13
- [Phase ?]: [11-01]: _sha256_hex extracted to app/core/_hashing.py as the single DRY source — verifier greps def _sha256_hex across app/ for exactly 1 hit; 11-02 api_key + 11-03 csrf/device_fingerprint import from here
- [Phase ?]: [11-01]: UserAlreadyExistsError takes no constructor arg; message hardcoded 'User with email already exists' (anti-enumeration leak via stack traces — threat T-11-03)
- [Phase ?]: [11-01]: RedactingFilter import sits at the bottom of app/core/logging.py with noqa: E402 — must run AFTER logging.config.dictConfig(config) which configures the named whisperX logger
- [Phase ?]: [11-02]: JWT sub claim serialized as str(user_id) per RFC 7519 §4.1.2 (PyJWT 2.x enforces); callers recover int via int(payload['sub'])
- [Phase ?]: [11-02]: rate_limit.consume on rejection bumps last_refill but preserves tokens — when rate=0 refill is no-op so tokens unchanged
- [Phase ?]: [11-02]: jwt.decode/jwt.encode locked to single site app/core/jwt_codec.py — verifier-enforced grep gate
- [Phase ?]: [11-03]: Domain layer framework-free verified — grep -rn 'from sqlalchemy' app/domain/ returns 0; entities, Protocols, mappers all pure Python
- [Phase ?]: [11-03]: SQLAlchemyApiKeyRepository.get_by_prefix uses idx_api_keys_prefix from Phase 10 + filters revoked_at IS NULL — KEY-08 + T-11-12 mitigated at persistence layer
- [Phase ?]: [11-03]: SQLAlchemyRateLimitRepository.upsert_atomic wraps read+write in text('BEGIN IMMEDIATE') for SQLite worker-safety — single RESERVED lock for the whole upsert (T-11-10)
- [Phase ?]: [11-03]: get_by_prefix returns list[ApiKey] (not Optional) — 8-char url-safe base64 prefix has tiny but non-zero collision probability; KeyService.verify iterates and uses secrets.compare_digest on hash to disambiguate
- [Phase ?]: [11-03]: DeviceFingerprint repository is insert+read-only — no update or delete methods (audit-trail design per ANTI-03); future plans wanting deletion must explicitly extend Protocol
- [Phase ?]: [11-04]: Per-service RED to GREEN TDD with 13 atomic commits; barrel deferred to last GREEN to avoid eager-import during incremental build
- [Phase ?]: [11-04]: TokenService SecretStr unwrap via config.provided.auth.JWT_SECRET.provided.get_secret_value.call() — dependency-injector 4.x supports the chain directly; no fallback adapter needed
- [Phase ?]: [11-04]: AuthService.login emits generic InvalidCredentialsError on both wrong-email and wrong-password legs — no enumeration via differential responses (T-11-13); skips verify_password on missing user (timing oracle accepted, ANTI-02 throttles to 10/hr/IP)
- [Phase ?]: [11-04]: DI Container lifecycle split — 3 Singletons (PasswordService, CsrfService, TokenService) + 3 Factories (AuthService, KeyService, RateLimitService) + 4 repo Factories binding session=db_session_factory
- [Phase ?]: [11-04]: KeyService.create_key returns plaintext exactly once (KEY-02 show-once UX); plaintext never logged; service stores prefix + sha256 hash via repo.add
- [Phase ?]: [11-05]: Phase 11 closes — 3 integration tests (15 cases): DI Container resolves all 6 auth services; Argon2 p99=34.7ms (88% headroom under 300ms budget); RedactingFilter scrubs sensitive structured fields end-to-end
- [Phase ?]: [12-01]: Stub command modules register placeholder @app.command()s rather than docstring-only — Typer 0.20+ refuses --help on registry with zero commands; plans 12-02/03 fully rewrite stubs anyway
- [Phase ?]: [12-01]: AuthService.register adds keyword-only plan_tier='trial' param — backward compat for 5 existing callers; admin bootstrap will pass plan_tier='pro' (verified by new unit test)
- [Phase ?]: [12-01]: app/cli/_helpers.py owns DRY surface — _get_container() factory + _resolve_admin(email, *, container=None) tiger-style fail-loud lookup; container kwarg is test seam for 12-02/03/04
- [Phase ?]: [12-02]: create-admin command catches `ValidationError` base (not `WeakPasswordError` directly) — open/closed; future ValidationError subclasses flow through same exit-1 path; `UserAlreadyExistsError` catch precedes generic `ValidationError` because UAE IS-A ValidationError (specific-first)
- [Phase ?]: [12-02]: Click 8.3.0 dropped `CliRunner(mix_stderr=False)` kwarg — Click 8.2+ separates stderr/stdout by default; `result.stderr` and `result.stdout` are independent attributes
- [Phase ?]: [12-02]: TDD RED help-test asserts `--email in stdout` (not `create-admin in stdout`) — plan-01 stub already registered the command name, so the original substring would have passed trivially; tightened to ensure RED genuinely fails on the stub
- [Phase ?]: [12-02]: getpass-only password discipline locked — verifier greps `password.*=.*typer\.` ==0 (no Typer Option), `getpass.getpass` ≥2 (entry+confirm), `logger.*password` ==0 (never logged); password mismatch fails BEFORE Container is built (no service-layer side effects)
- [Phase ?]: [12-03]: backfill-tasks engine.begin() three-step transaction — count_before/UPDATE/count_after; raising typer.Exit(1) inside the with-block triggers ROLLBACK on post-verify failure (tiger-style fail-loud + automatic data restore)
- [Phase ?]: [12-03]: 'assume_yes or typer.confirm(...)' short-circuit collapses Guard 3 into single boolean expression; typer.confirm default=False (dangerous default goes safe direction)
- [Phase ?]: [12-03]: Module-scope SQL constants _COUNT_ORPHANS_SQL + _UPDATE_SQL — count fragment reused pre-flight+post-condition (DRT); UPDATE uses :admin_id bound parameter
- [Phase ?]: [12-04]: 0003 migration pre-flight orphan guard — bind.execute SELECT COUNT(*) FROM tasks WHERE user_id IS NULL; raises RuntimeError if > 0; refuses to alter column rather than fail mid-batch (CONTEXT 138 tiger-style)
- [Phase ?]: [12-04]: e2e integration test uses subprocess (not in-process CliRunner) because SQLAlchemy engine binds DB_URL at module-load; subprocess re-imports against tmp DB. Pattern matches Phase 10 test_alembic_migration.py
- [Phase ?]: [12-04]: Windows getpass.getpass cannot be piped via subprocess; msvcrt.getwch reads keyboard directly. Test-only -c preamble monkey-patches getpass.getpass BEFORE app.cli imports. Production source untouched (CONTEXT 141)
- [Phase ?]: [13-01]: slowapi 0.1.9 + stripe 15.1.0 added; stripe imported at module-load only per BILL-07 (zero runtime calls in v1.2)
- [Phase ?]: [13-01]: AuthSettings extended with 8 Phase-13 envs (V2_ENABLED, FRONTEND_URL, COOKIE_SECURE/DOMAIN, TRUST_CF_HEADER, HCAPTCHA_*); validator refuses boot when V2 + localhost FRONTEND_URL or COOKIE_SECURE=false
- [Phase ?]: [13-01]: app/core/feature_flags.py single source for is_auth_v2_enabled / is_hcaptcha_enabled; flat returns, no nested-if (DRY — downstream never imports AuthSettings directly)
- [Phase ?]: [13-01]: data/disposable-emails.txt bundled with 5413 entries from disposable-email-domains GitHub master (deterministic boot); loader scheduled for Plan 13-03
- [Phase ?]: [13-02]: DualAuthMiddleware decodes cookie JWT once via jwt_codec.decode_session (recover sub) then delegates to TokenService.verify_and_refresh — verifier-checked grep jwt.decode( returns 0; bearer wins resolution order locked
- [Phase ?]: [13-02]: PUBLIC_ALLOWLIST 13 paths locked from MID-03 (/health/* /openapi.json /docs /redoc /static /favicon.ico /auth/{register,login} /ui/{login,register} /); PUBLIC_PREFIXES adds /static/ + /uploads/files/ for nested static + tus uploads
- [Phase ?]: [13-02]: Single 401 detail string 'Authentication required' for ALL bearer/cookie/missing-auth failures (T-13-05); WWW-Authenticate Bearer realm header on 401
- [Phase ?]: [13-02]: CsrfMiddleware uses getattr(request.state, auth_method, None) defensively — if mounted before DualAuthMiddleware (mis-order) the None fallback safely bypasses; STATE_MUTATING_METHODS=POST/PUT/PATCH/DELETE only
- [Phase ?]: [13-02]: 5 new auth dependencies appended to app/api/dependencies.py — get_authenticated_user (defence-in-depth 401), get_current_user_id, get_csrf_service/key_service/auth_service/rate_limit_service; reused across all Phase 13 routes (DRT)
- [Phase ?]: [13-03]: app/core/disposable_email.py loads data/disposable-emails.txt (5413 entries) into module-load frozenset[str]; is_disposable() lowercases domain for O(1) check; fail-soft on missing file
- [Phase ?]: [13-03]: app/core/rate_limiter.py exposes singleton `limiter = Limiter(key_func=_client_subnet_key)`; key_func resolves CF-Connecting-IP/X-Forwarded-For (gated on AUTH__TRUST_CF_HEADER) then ipaddress.ip_network groups IPv4→/24 IPv6→/64; rate_limit_handler emits 429 + Retry-After (RATE-12)
- [Phase ?]: [13-03]: auth_router defined with prefix="/auth"; register (3/hr/IP/24, ANTI-01), login (10/hr/IP/24, ANTI-02), logout (idempotent 204); _set_auth_cookies + _clear_auth_cookies DRY helpers; cookie attrs from settings.auth.{COOKIE_SECURE, COOKIE_DOMAIN, JWT_TTL_DAYS}; not yet mounted (plan 13-09 atomic flip)
- [Phase ?]: [13-03]: Anti-enumeration: identical 422 body+code "Registration failed/REGISTRATION_FAILED" on disposable + duplicate registration legs (T-13-09); shared InvalidCredentialsError on wrong-email + wrong-password (T-13-10) — verified by integration tests comparing both leg shapes
- [Phase ?]: [13-03]: /auth/logout returns a fresh Response with cookies cleared (NOT the injected Response param) — FastAPI ignores injected Response when handler returns explicit Response, dropping Set-Cookie deletions. Caught by test_logout_clears_cookies; fixed inline as Rule 1 bug
- [Phase ?]: [13-03]: invalid_credentials_handler defined in app/api/exception_handlers.py (maps InvalidCredentialsError → 401); registration in plan 13-09 alongside RateLimitExceeded + ValidationError handlers
- [Phase ?]: [13-03]: email-validator>=2.0.0 pinned in pyproject.toml — required by pydantic EmailStr at validation time (foreseen in plan body as fallback action)
- [Phase ?]: [13-03]: Test isolation: per-test Container with providers.Factory(sessionmaker(bind=tmp_engine)) override + limiter.reset() in setup AND teardown; slim FastAPI app (no main.py legacy middleware) keeps tests independent of plan 13-09 wiring
- [Phase ?]: [13-04]: AuthService.start_trial_if_first_key takes count as parameter (not derived) — keeps service free of ApiKey-repository knowledge (SRP); three flat guards; idempotent on subsequent creations
- [Phase ?]: [13-04]: Cross-user DELETE 404 mechanism uses list_for_user-then-filter — KeyService.list_for_user already scopes to user_id; foreign keys never appear in candidate list (T-13-15); identical 404 body for missing-id and foreign-id
- [Phase ?]: [13-04]: Show-once UX enforced at TWO layers — route returns key=plaintext only in CreateKeyResponse; ListKeyItem schema lacks key field entirely (Pydantic discards on serialize, defence-in-depth)
- [Phase ?]: [13-04]: Integration tests use TWO TestClient instances for cross-user (separate cookie jars same app+DB); bearer auth path bootstraps via cookie POST then re-issues plaintext as Authorization: Bearer
- [Phase ?]: [13-05]: AccountService.delete_user_data takes raw Session (not ITaskRepository) — bulk DELETE via text() with bound :uid is leak-proof (no ORM cascade surprise); does NOT depend on Phase 13-07
- [Phase ?]: [13-05]: get_db_session generator added to dependencies.py — yields managed Container.db_session_factory() session for non-repository services; closes on exit; Phase 15 SCOPE-06 full-row delete composes against this helper
- [Phase ?]: [13-05]: PUBLIC_ALLOWLIST extended with /billing/webhook (Rule 3 deviation) — Stripe calls server-to-server; authenticity is via Stripe-Signature HMAC (v1.3); schema-check at 400 is the v1.2 security boundary
- [Phase ?]: [13-05]: Stripe-Signature regex t=<unix>,vN=<hex>,?+ validates schema only (rejects malformed/spam at 400); v1.3 replaces with stripe.Webhook.construct_event for full HMAC verification
- [Phase ?]: [13-05]: BILL-07 import stripe at module-load — verifier-checked zero runtime stripe.*() calls in app/; v1.2 dependency tree resolves identically to v1.3 build
- [Phase ?]: WS ticket store: in-memory dict + threading.Lock; single-worker scope per CONTEXT §93. Multi-worker requires Redis (deferred).
- [Phase ?]: Defence-in-depth MID-07: WS handler re-checks consumed_user_id == task.user_id after consume() — protects against future tasks.user_id drift.
- [Phase ?]: Domain Task.user_id surfaced as int|None; ORM column nullable until full Phase 12 backfill verification (tightening to NOT NULL is Phase 12 remediation).
- [Phase ?]: [13-07]: ITaskRepository.set_user_scope is request-bound state on the repo (Factory provider gives a fresh instance per request); _scoped_query() funnel powers get_by_id/get_all/update/delete (DRT)
- [Phase ?]: [13-07]: Default _user_scope=None preserves Phase 12 CLI/admin backward compat; HTTP routes always go through get_scoped_task_repository which sets+clears scope per request (T-13-33 defence-in-depth)
- [Phase ?]: [13-07]: Fail-loud add() refuses to persist task with no owner (ValueError when user_id is None|0 AND _user_scope is None) — closes T-13-34 silent orphan write
- [Phase ?]: [13-07]: Cross-user 404 (not 403) — bytewise body parity with unknown-uuid 404 verified in test_cross_user_delete_returns_same_404_body_as_unknown_id (anti-enumeration)
- [Phase ?]: [13-07]: ws_ticket_routes manual task.user_id != user.id check kept as defence-in-depth even though scoped repo already returns None for cross-user — catches future drift if a task's user_id mutates post-issue (MID-07)
- [Phase ?]: [13-07]: get_scoped_task_management_service constructs TaskManagementService(scoped_repo) per request — task_api.py routes get scoping for free without any service-layer changes (SRP)
- [Phase ?]: 13-08 release method capacity-cap
- [Phase ?]: [13-08]: FreeTierGate W1 contract — concurrency slot consumed at transcribe-START via _check_concurrency (rate=0 so true semaphore) and ALWAYS released in process_audio_common try/finally (success AND failure paths) via release_concurrency(user); user re-loaded from task.user_id in finally for slim BackgroundTask payload
- [Phase ?]: [13-08]: Rule 1 latent-bug fix in rate_limit_bucket_mapper — SQLite strips tzinfo from DateTime(timezone=True) on round-trip; consume() math then crashes on tz-aware now minus tz-naive last_refill; mapper now reattaches UTC tzinfo on read
- [Phase ?]: [13-08]: DiarizationParams in v1.2 has only min_speakers/max_speakers (no boolean .diarize) — gate's diarize arg derived as 'either bound is set' so /speech-to-text remains accessible to free tier while explicit speaker-bound requests trigger 403 pro-only guard
- [Phase ?]: [13-08]: usage_events.idempotency_key=task.uuid + UNIQUE — IntegrityError caught + rollback for replay safety (T-13-40 v1.3 Stripe metering); usage_events.task_id NULL since the FK is redundant for v1.2 metering — backfill is a one-line lookup if v1.3 needs it
- [Phase 13]: [13-09]: app/core/auth.py recreated (was missing from disk; initial git status snapshot stale) — minimal legacy BearerAuthMiddleware + W4 DEPRECATED header; fail-CLOSED on unset API_BEARER_TOKEN
- [Phase 13]: [13-09]: Atomic flip wiring — single is_auth_v2_enabled() check at app boot decides middleware stack (DualAuth+CSRF vs BearerAuth) AND router registration (5 Phase 13 routers gated); CORS locked to FRONTEND_URL with allow_credentials=True in BOTH branches
- [Phase 13]: [13-09]: Production-safety boot guard refuses to start when ENVIRONMENT=production AND AUTH_V2_ENABLED=false (T-13-43); slowapi limiter mounted unconditionally on app.state for @limiter.limit decorators on auth routes; 6 typed exception handlers registered in BOTH branches
- [Phase ?]: [13-10]: Subprocess-per-test e2e smoke gate (uvicorn + tmp SQLite + alembic upgrade head); 12/12 tests pass in 233s; gates Phase 13 atomic deploy with Phase 14 frontend
- [Phase ?]: [13-10]: Rule 3 fix to app/docs.py — utf-8 explicit on save_openapi_json + write_markdown_to_file (Windows cp1252 was hanging subprocess lifespan on non-ASCII docstring chars)
- [Phase ?]: [13-10]: V2_OFF fixture sets API_BEARER_TOKEN + sends bearer header so legacy middleware passes through; route NOT registered surfaces as 404 (must-have signal vs 401 auth-missing)
- [Phase ?]: [14-01]: Vitest config split into vitest.config.ts (separate from vite.config.ts) — SRP; build vs test concerns isolated
- [Phase ?]: [14-01]: BroadcastChannel polyfill rewritten as peer-instance registry — plan-prescribed boundListener single-field design was broken; per-channel Map<name,Set<instance>> + per-instance Set<listener> delivers correct cross-instance fan-out (Rule 1 deviation)
- [Phase ?]: [14-01]: MSW handlers split per resource (auth.handlers/keys.handlers/ws.handlers) re-exported from handlers.ts barrel — DRY for Plans 14-02..07 imports
- [Phase ?]: [14-01]: shadcn primitives (form/input/label/dialog/alert) written verbatim from new-york canonical source (no shadcn CLI invocation) — deterministic, no TTY dep; existing badge/button/card/collapsible/progress/scroll-area/select/sonner/tooltip preserved
- [Phase ?]: [14-01]: bunx msw init public/ generated mockServiceWorker.js + added msw.workerDirectory pin to package.json — both kept (canonical practice)
- [Phase ?]: [14-02]: apiClient is the SINGLE fetch() site — Plans 03-07 import { apiClient } only; Plan 07 refactors 3 existing direct-fetch sites to drop to 0
- [Phase ?]: [14-02]: Typed error hierarchy (ApiClientError/AuthRequiredError/RateLimitError) — callers narrow via instanceof; tiger-style
- [Phase ?]: [14-02]: 401 uses module-level _redirectingTo401 latch (T-14-05); suppress401Redirect for authStore.refresh() boot probe

### Pending Todos

- Phase 10 plan-phase (next step: `/gsd-plan-phase 10`)

### Blockers/Concerns

- Single shared `API_BEARER_TOKEN` middleware blocks frontend until v1.2 Phase 13+14 atomic cutover lands
- tuspyserver fcntl patch is dev-only (Windows); production Linux is unaffected
- tuspyserver file.py patch (gc_files) needs reapplication after pip install
- Cloudflare WAF rules need validation in staging (deferred to v1.3 — was v1.1 phase 10)
- Phase 13/14 atomicity: half-deploy risk — must use feature flag and single release window

## Session Continuity

Last session: 2026-04-29T13:27:32.487Z
Stopped at: Plan 14-01 complete — Vitest+jsdom+RTL+MSW infra online; shadcn primitives + zustand/RHF/zod deps installed; sentinel 2/2; 2 commits (b0de895, dff607a)
Resume file: None
