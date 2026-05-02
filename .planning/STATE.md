---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: milestone
status: executing
stopped_at: Completed 19-01-PLAN.md
last_updated: "2026-05-02T15:53:40.886Z"
last_activity: 2026-05-02
progress:
  total_phases: 10
  completed_phases: 8
  total_plans: 62
  completed_plans: 49
  percent: 79
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-29)

**Core value:** Users can sign up, get API keys, and use WhisperX via browser or external API with free-tier limits and Stripe-ready billing
**Current focus:** Phase 19 — Auth + DI Structural Refactor

## Current Position

Phase: 19 (Auth + DI Structural Refactor) — EXECUTING
Plan: 4 of 17 (next: 19-02 services.py @lru_cache singletons)
Status: Ready to execute
Last activity: 2026-05-02

Prior position: Phase 17 complete 2026-05-01; Phase 18 closed empty 2026-05-01.

## Performance Metrics

**Velocity (v1.1 final):**

- Total plans completed: 38 (v1.1)
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
| 14 | 7 | - | - |

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
| Phase 14 P03 | 3m 46s | 2 tasks | 3 files |
| Phase 14 P04 | 4m 9s | 2 tasks | 17 files |
| Phase 14 P05 | 5m 30s | 2 tasks | 10 files |
| Phase 14 P06 | 5m 28s | 2 tasks | 9 files |
| Phase 14 P07 | 4m 28s | 3 tasks | 7 files |
| Phase 15 P01 | 9 min | 3 tasks | 9 files |
| Phase 15 P02 | 4 min | 1 task (TDD) | 2 files |
| Phase 15 P03 | 6 min | 2 tasks (3 commits, TDD) tasks | 3 files files |
| Phase 15 P04 | 9 min | 3 tasks | 3 files |
| Phase 15 P05 | 9 min | 2 tasks (TDD) tasks | 7 files files |
| Phase 15 P06 | 7 min | 2 tasks | 8 files |
| Phase 16 P01 | 3 min | 2 tasks | 1 files |
| Phase Phase 16 PP04 | 3 min | 2 tasks | 1 files |
| Phase 16 P06 | 5 min | 2 tasks | 1 files |
| Phase 16 P05 | 7min | 2 tasks | 1 files |
| Phase 17 P01 | 3min | 1 tasks | 1 files |
| Phase 17 P02 | 1min | 1 tasks | 1 files |
| Phase 17 P03 | 4min | 1 tasks | 1 files |
| Phase 19 P01 | 8min | 1 tasks | 1 files |
| Phase 19 P02 | 16min | 2 tasks | 2 files |
| Phase 19 P03 | 10min | 2 tasks | 2 files |

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
- [Phase ?]: [14-03]: AuthUser.email held client-side from form input (not from /auth/login response) — backend v1.2 returns only user_id+plan_tier; CONTEXT §70-72 locked. Plan 15 /api/account/me will server-side override.
- [Phase ?]: [14-03]: register() broadcasts {type:'login'} (not 'register') — locks cross-tab protocol to 2 message types: login | logout (DRY)
- [Phase ?]: [14-03]: refresh()/hydration deferred to Phase 15 — no /api/account/me yet. Cookie session persists 7d but in-memory user null on reload; RequireAuth (14-04) redirects via /login?next=
- [Phase ?]: [14-03]: Lazy _channel sentinel in authStore — BroadcastChannel constructed only on first state action; tolerates stray-import side effects + SSR/Node paths
- [Phase ?]: [14-03]: toAuthUser(response, email) helper — DRY mapping shared by login()/register(); single extension point for Phase 15 AuthUser fields
- [Phase ?]: [14-04]: AppShell wraps /dashboard/* only — / (TranscribePage) renders without it to preserve UploadDropzone full-bleed layout (UI-10 zero-regression)
- [Phase ?]: [14-04]: Catch-all path='*' Navigates to / (replace); RequireAuth then handles unauth /login?next= redirect — saves a dedicated 404 page in v1.2
- [Phase ?]: [14-04]: PageWrap DRY composer wraps RouteErrorBoundary + Suspense around every route element — 1-line route registration; impossible to ship a page without per-route ErrorBoundary
- [Phase ?]: [14-04]: Lazy named-export shim — lazy(() => import('./X').then((m) => ({default: m.X}))) — Plans 05/06 ship named exports; routes/ stays consistently named-export
- [Phase ?]: [14-04]: Rule 3 fix — apiErrors.ts + setup.ts constructor parameter properties rewritten to explicit field declarations to satisfy tsconfig erasableSyntaxOnly (was pre-existing build break from 14-01/14-02)
- [Phase ?]: [14-05]: Pure roll-our-own zxcvbn-style scorer (no external library) — cumulative bands {len>=8, mixed-case, digit, symbol, len>=16} capped at 4; pure function, 8/8 boundary tests, swap path to real zxcvbn preserved
- [Phase ?]: [14-05]: AuthCard layout shell shared by /login + /register only — dashboards (Plan 14-06) live in AppShell instead; AuthCard is the locked layout for credential-collection pages
- [Phase ?]: [14-05]: FormFieldRow DRY primitive (text-input rows only) — bespoke FormField for terms checkbox is a deliberate non-DRY exception (different layout); FormCheckboxRow extraction deferred until 3+ checkbox rows exist
- [Phase ?]: [14-05]: Anti-enumeration error funnel — RateLimitError handled BEFORE ApiClientError in catch chain (subtype-first); single generic 'Login failed.' / 'Registration failed.' string regardless of backend code/detail (T-14-12 mitigation)
- [Phase ?]: [14-05]: Native input type=checkbox for termsAccepted — no shadcn Checkbox component shipped; native input + manual styling keeps Plan 14-05 zero-dep, swappable later
- [Phase ?]: [14-05]: Rule 1 fix — AppRouter.test.tsx assertions migrated from placeholder text ('LoginPage placeholder' / 'RegisterPage placeholder') to heading-role queries ('Sign in' / 'Create account'); placeholder text was a transient Plan 14-04 artifact, heading-role survives copy reshuffles
- [Phase ?]: Plan 14-06: KeysDashboardPage two-state CreateKeyDialog (form -> show-once) keeps plaintext in component state only (T-14-15); reset() clears on close
- [Phase ?]: Plan 14-06: Trial countdown derives client-side from earliest active key + 7d (RATE-08 proxy until Phase 15 /api/account/me)
- [Phase ?]: Plan 14-06: vi.spyOn(navigator.clipboard, 'writeText') AFTER userEvent.setup() - robust clipboard test pattern under user-event v14
- [Phase ?]: [14-07]: GLOBAL ZERO-FETCH GATE locked — apiClient.ts is the SOLE fetch() site in frontend/src; 3 prior direct-fetch sites (taskApi, transcriptionApi, useTaskProgress) eliminated; CI-grep-enforceable invariant
- [Phase ?]: [14-07]: ApiResult<T> external shape preserved across cutover — consumers (FileQueueItem.tsx, useUploadOrchestration.ts) unchanged; internal fetch->apiClient swap invisible to UI code
- [Phase ?]: [14-07]: WS ticket-aware socketUrl is useState seeded by useEffect on taskId; null gates connection until ticket lands; onClose+reconnect re-issue tickets unconditionally for single-use compliance (T-14-19 client mitigation)
- [Phase ?]: [14-07]: TEST-06 floor is 3 smoke assertions (CTA, file-add, start-affordance); deeper progress->complete chain has non-deterministic timing — Phase 16 owns Playwright E2E for the full chain
- [Phase ?]: [14-07]: MockWebSocket inline class via vi.stubGlobal in smoke.test.tsx — kept inside test file, not extracted to setup.ts (premature-abstraction guard until 3+ tests need it)
- [Phase ?]: [14-07]: Catch chain order locked: AuthRequiredError rethrown -> RateLimitError -> ApiClientError -> generic Error; subtype-first keeps rate-limit branch reachable (RateLimitError extends ApiClientError)
- [15-01]: apiClient.get migrated to opts object {headers, suppress401Redirect}; apiClient.delete accepts body — public exports object owns the API surface (request() core unchanged from Phase 14-02)
- [15-01]: clear_auth_cookies extracted to app.api._cookie_helpers as the public DRY source — SESSION_COOKIE/CSRF_COOKIE constants relocated; auth_routes.py imports the shared helper; no leading underscore on cross-module helper (tiger-style)
- [15-01]: account_schemas.py uses Pydantic v2 EmailStr field allowlist (T-15-11) — only id/email/plan_tier/trial_started_at/token_version cross the wire; submitUpgradeInterest left bare (no try/catch) so caller in Wave 2 UpgradeInterestDialog catches ApiClientError statusCode===501 as success per T-15-07
- [15-02]: POST /auth/logout-all is a glue route only — service layer (AuthService.logout_all_devices) already validates user existence and atomically bumps token_version; route does HTTP only (4 statements, zero `if`s, SRP locked). Mirror /auth/logout fresh-Response pattern (T-15-04): `response = Response(204); clear_auth_cookies(response); return response` — never reuse Depends-injected Response or Set-Cookie deletions get dropped.
- [15-02]: Test fixture choice locked Option A (PATTERNS.md) — added a NEW `auth_full_app` fixture mounting DualAuthMiddleware to test_auth_routes.py rather than mutating the slim `auth_app` fixture (would 401 the existing test_logout_idempotent because /auth/logout is NOT in PUBLIC_ALLOWLIST). Net: zero regression on the 12 existing auth tests.
- [15-02]: JWT-invalidation test cookie-snapshot pattern — the 204 response clears the client-side cookie, so the natural next-request would be anonymous (401 for the wrong reason). Snapshot the cookie BEFORE logout-all then re-attach via `client.cookies.set('session', old_session_cookie)` to exercise ver=N JWT vs server-side ver=N+1 explicitly (token_version invariant verified, T-15-03 mitigation tested end-to-end).
- [15-02]: Acceptance criterion AC5 (`grep -c "Depends(Response)" auth_routes.py == 0`) flagged a docstring containing the literal anti-pattern phrase — verifier-grep doesn't distinguish docstrings from code. Rule 1 fix: paraphrased docstring to `"see logout above for rationale"` without the literal token. Pattern: keep verifier-grep gates literal-token-clean even in comments.
- [Phase 15]: [15-03]: AccountService.__init__ accepts user_repository: IUserRepository | None — None lazy-constructs SQLAlchemyUserRepository(session) preserving Phase-13 SCOPE-05 backward compat (DRT); Plan 15-04 delete_account reuses _user_repository (DRY)
- [Phase 15]: [15-03]: get_account_summary returns dict (not domain entity) so route wraps via AccountSummaryResponse(**summary) — keeps service Pydantic-free, mirrors Phase 13-04 CreateKeyResponse(**dict) idiom (SRP)
- [Phase 15]: [15-03]: User-not-found → InvalidCredentialsError → 401 (not 404) for anti-enumeration parity with auth failures (T-15-05); response_model=AccountSummaryResponse enforces T-15-11 field allowlist (no password_hash leak)
- [Phase ?]: [15-04]: Strategy C LOCKED — service-orchestrated 3-step cascade (delete_user_data → DELETE rate_limit_buckets prefix-match → user_repository.delete fires ORM CASCADE for 4 CASCADE FKs); tasks.user_id NOT NULL after migration 0003 forbids bare user delete (Pitfall 2)
- [Phase ?]: [15-04]: ValidationError → 400 EMAIL_CONFIRM_MISMATCH translated route-locally via HTTPException; global validation_error_handler default 422 preserved for register/login flows (Option B route-local, RESEARCH §1252)
- [Phase ?]: [15-04]: T-15-03 LOCKED — no token_version bump on delete; user-row-gone is the invalidation signal (middleware get_by_id returns None on next request → 401). Cookie clearing is route-level UX cleanup, not a security gate.
- [Phase ?]: [15-04]: Rule-1 test fix — Starlette TestClient.delete() does not accept json= kwarg in this httpx version; all 6 delete-with-body tests use client.request('DELETE', url, json=...). Pattern recorded for future DELETE-with-body tests.
- [Phase ?]: [15-05]: refresh() error-class branch narrows on AuthRequiredError + ApiClientError; truly unexpected errors propagate (T-15-04 mitigation); isHydrating still flips via finally on every code path
- [Phase ?]: [15-05]: Module-scope boot probe void useAuthStore.getState().refresh() in main.tsx (BEFORE createRoot.render) — StrictMode-safe single-fire (useEffect would double-hydrate)
- [Phase ?]: [15-05]: RequireAuth 3-state gate uses two flat early-return guards (isHydrating then user===null) — fail-closed null render; nested-if invariant 0 across all 5 modified files
- [Phase ?]: [15-05]: 3 sibling test files (AppRouter, KeysDashboardPage, smoke) updated to seed full AuthUser shape (Rule 3 deviation — TS strict compile gate); AppRouter helper migrated to import AuthUser type (DRY single source)
- [Phase 15]: [15-06]: AccountPage three-card layout (Profile/Plan/Danger Zone) with PLAN_BADGE_VARIANT + PLAN_COPY narrowed Record<plan_tier,...> + 'Plan details unavailable.' fallback for unknown values (T-15-10 mitigation); inline-styled native textarea in UpgradeInterestDialog (no shadcn primitive vendored); isMatched gate adds && userEmail.length > 0 defence-in-depth — Locked design contract executed verbatim per UI-SPEC §116-160; tiger-style boundary defence; matches sibling KeysDashboardPage pattern.
- [Phase 15]: [15-06]: setTimeout-spy assertion pattern for auto-close timer test (UpgradeInterestDialog) — fake timers deadlock against MSW response promises in this codebase; spy + invoke-callback-directly + act() is more precise than wall-clock and side-steps the deadlock — Discovered during Task 2 — 5000ms timeout on findByText after vi.useFakeTimers() with MSW pending. Pattern saves ~2s per test run vs real-timer wait.
- [Phase 16]: [16-01]: ENDPOINT_CATALOG hardcoded as module-level constant (not env-driven) — DRT single source for VERIFY-01 cross-user matrix and VERIFY-06 CSRF surface; status semantics 200 (caller-scoped own namespace) / 204 (write on caller's empty namespace) / 404 (anti-enumeration opaque)
- [Phase 16]: [16-01]: _forge_jwt three deterministic branches via flat early-returns (no nested-if): alg=none bypasses PyJWT (refuses on encode), HS256+expired uses real signing with iat/exp shifted to past, HS256+tamper flips last sig char post-jwt.encode
- [Phase 16]: [16-01]: Lazy ORMTask import inside _insert_task — module-level import would require DB engine bound at import time; lazy keeps module loadable for plans needing only _forge_jwt or _run_alembic
- [Phase 16]: [16-01]: _seed_two_users(client_a, client_b) → tuple[int, int] interface (per plan <interfaces> block) — caller owns TestClient construction so each test shapes its own jar isolation; PATTERNS.md alternative (app, session_factory) signature rejected in favor of plan-specified contract
- [Phase Phase 16]: [16-04]: VERIFY-06 4 CSRF cases land on /auth/logout-all (single CSRF target via _csrf_target_endpoint helper); ASGI order locked CsrfMiddleware-first DualAuth-last so dispatch is DualAuth->Csrf->route; bearer-bypass test uses cookie-auth path to issue API key then client.cookies.clear() before bearer POST for unambiguous test signal — DRY single source for path + tiger-style detail-string asserts on 403 cases + nested-if grep == 0
- [Phase 16]: [16-06]: VERIFY-08 brownfield migration smoke uses 4-step sequence (build legacy → stamp 0001 → upgrade 0002_auth_schema → seed admin + UPDATE tasks.user_id → upgrade head) — 0003 NOT NULL pre-flight requires ALL tasks.user_id non-null BEFORE upgrade head, otherwise RuntimeError. Mirrors Phase 17 OPS-03 operator runbook exactly.
- [Phase 16]: [16-06]: Rule 1 fix — plan PROMPT specified `hashed_password` column but actual schema (0002_auth_schema.py:42 + models.py:177) uses `password_hash`. INSERT corrected before write; tracked as plan/code drift bug.
- [Phase 16]: [16-06]: Fresh-engine FK-enforcement test must enable PRAGMA foreign_keys=ON manually — production engine listener (Phase 10-04) attaches to global engine only; tmp_path engines created via local create_engine() get default OFF. Inline pragma + comment documents the divergence.
- [Phase 16]: [16-06]: DRY: _run_alembic + REPO_ROOT imported from tests/integration/_phase16_helpers (Plan 10-04 venv-portable subprocess pattern); test file is 206 lines with ZERO copy-paste of alembic CLI plumbing
- [Phase 16]: Cross-user drift target must be FK-valid (PRAGMA foreign_keys=ON from 10-04 forbids non-existent ids); test registers User B and drifts to user_id_b not 9999 — FK constraint failure was Rule 1 bug found mid-execution; deviation lock for future drift-style tests
- [Phase 16]: monkeypatch.setattr(...) MUST stay on a single line for verifier grep gate compliance — line-wrap dropped grep -c count from 1 to 0 — verifier greps are per-line literal matches; multi-line Python style breaks them
- [Phase ?]: [17-01]: docs/migration-v1.2.md locked 9-section skeleton (Purpose / Pre-flight / Command / Expected output / Verify / Failure mode per section); step ordering 1:1 mirrors test_migration_smoke.py (VERIFY-08 executable proof); revision IDs listed once in Section 1 chain table (DRY); Windows getpass-piping limitation kept inline in Section 5; Rollback split flat option-A (alembic downgrade chain) vs option-B (full backup restore)
- [Phase ?]: [17-02]: bare env var names in .env.example match ROADMAP success criterion 2 verbatim; AUTH__ prefix translation per existing Notes block (DRT — single-source operator-facing surface)
- [Phase ?]: [17-03]: README.md gains `## Authentication & API Keys (v1.2)` top-level section between Web UI block and v1.0 prose; PLAN-prescribed locked block honored verbatim (text flow diagram + 5 subheadings + 3 curl snippets + free-vs-Pro 5-row table + mailto:hey@logingrupa.lv reset link + cross-link to docs/migration-v1.2.md); DRY enforced cross-file (zero migration command bodies, zero env-var declarations in README); insert-only edit preserves existing structure byte-for-byte; OPS-05 closed; Phase 17 closes (OPS-03/04/05 all delivered)
- [Phase 19]: [19-01]: pytest --collect-only must use -qq (not -q) on pytest 9.0.3 — only -qq emits flat path::Class::method nodeids; -q emits hierarchical <Module>/<Function> tree. Baseline filter regex anchors `^[A-Za-z0-9_./\\-]+\.py::[A-Za-z0-9_:\\-]+(\[.+\])?$` keeps parametrized cases.
- [Phase 19]: [19-01]: factory-boy 3.3.3 missing from .venv even though declared in pyproject.toml:63 — installed at execution time so 4 test modules (test_task_lifecycle, test_task, test_task_mapper, test_sqlalchemy_task_repository) collect; baseline rose from 455+4errors to 500 collected. Operator/CI must `uv sync` to pick up.
- [Phase 19]: [19-01]: DEVIATIONS.md was already committed in plan-phase commit 2e89924; T-19-01 commits the baseline file alone (single commit b83d3d8). Plan's `git log -1 --name-only shows both files in the same commit` gate is inapplicable; logical pair is intact across two commits, individual gates (>=500 lines + grep waiver entry) both pass.
- [Phase ?]: [Phase 19]: [19-02]: app/core/services.py created with 9 lru-cached singleton factories — D1 replacement pattern locked; ML services lazy-imported inside factory body (CLI/migration paths free of PyTorch/whisperx/pyannote import cost); existing app/core/container.py untouched (Plans 03..12 migrate callsites incrementally)
- [Phase ?]: [Phase 19]: [19-02]: docstring grep-gate tax — verifier 'grep -c | grep -q 9' counts every literal '@lru_cache(maxsize=1)' on every line; rephrase docstring to 'lru-cached'/'functools.lru_cache' (Rule 1 fix). Same lesson as Plan 15-02: keep verifier-grep-gate tokens code-only
- [Phase ?]: [Phase 19]: [19-03]: get_db generator + 12 _v2 providers (5 repo + 7 service) added to app/api/dependencies.py — single request-scope session.close() site (db.close() == 1); legacy _container.X() helpers untouched (coexistence per Plan 12); 15 unit tests GREEN, full suite 495 passed (zero regression vs Plan 02 baseline)
- [Phase ?]: [Phase 19]: [19-03]: scoped task repo + task_management_service deferred to Plan 04 — both depend on authenticated_user.set_user_scope; Plan 03 stops at 5 unscoped repos + 7 stateless services per planner action block. AccountService factory passes both session + user_repository per Plan 15-03 deviation lock (single repo instance shared across methods, DRY)

### Pending Todos

- Phase 10 plan-phase (next step: `/gsd-plan-phase 10`)

### Blockers/Concerns

- Single shared `API_BEARER_TOKEN` middleware blocks frontend until v1.2 Phase 13+14 atomic cutover lands
- tuspyserver fcntl patch is dev-only (Windows); production Linux is unaffected
- tuspyserver file.py patch (gc_files) needs reapplication after pip install
- Cloudflare WAF rules need validation in staging (deferred to v1.3 — was v1.1 phase 10)
- Phase 13/14 atomicity: half-deploy risk — must use feature flag and single release window

## Session Continuity

Last session: 2026-05-02T15:53:32.688Z
Stopped at: Completed 19-01-PLAN.md
Resume file: None
