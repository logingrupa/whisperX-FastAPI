---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: milestone
status: executing
stopped_at: Plan 12-01 complete — Typer CLI scaffold + DRY helpers + AuthService.register plan_tier kwarg (typer 0.20.0; 6/6 AuthService tests; df1e402)
last_updated: "2026-04-29T07:07:16.954Z"
last_activity: 2026-04-29
progress:
  total_phases: 9
  completed_phases: 2
  total_plans: 13
  completed_plans: 10
  percent: 77
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-29)

**Core value:** Users can sign up, get API keys, and use WhisperX via browser or external API with free-tier limits and Stripe-ready billing
**Current focus:** Phase 12 — Admin CLI + Task Backfill

## Current Position

Phase: 12 (Admin CLI + Task Backfill) — EXECUTING
Plan: 2 of 4
Status: Ready to execute
Last activity: 2026-04-29

## Performance Metrics

**Velocity (v1.1 final):**

- Total plans completed: 17 (v1.1)
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

### Pending Todos

- Phase 10 plan-phase (next step: `/gsd-plan-phase 10`)

### Blockers/Concerns

- Single shared `API_BEARER_TOKEN` middleware blocks frontend until v1.2 Phase 13+14 atomic cutover lands
- tuspyserver fcntl patch is dev-only (Windows); production Linux is unaffected
- tuspyserver file.py patch (gc_files) needs reapplication after pip install
- Cloudflare WAF rules need validation in staging (deferred to v1.3 — was v1.1 phase 10)
- Phase 13/14 atomicity: half-deploy risk — must use feature flag and single release window

## Session Continuity

Last session: 2026-04-29T07:07:16.948Z
Stopped at: Plan 12-01 complete — Typer CLI scaffold + DRY helpers + AuthService.register plan_tier kwarg (typer 0.20.0; 6/6 AuthService tests; df1e402)
Resume file: None
