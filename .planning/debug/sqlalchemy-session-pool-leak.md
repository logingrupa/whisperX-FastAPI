---
slug: sqlalchemy-session-pool-leak
status: resolved
trigger: |
  Login slow / 401 after correct password reported across multiple debug
  sessions (login-401-slow-response, login-correct-pw-30s-401,
  login-stuck-loading). Prior sessions chased frontend symptoms. Root cause
  identified by user-supplied diagnosis: SQLAlchemy session leak in
  app/api/dependencies.py — get_auth_service / get_csrf_service /
  get_key_service / get_rate_limit_service (lines 223-248) return services
  without yield + finally session.close(). Each request leaks a Session.
  After 15 leaks the default QueuePool(size=5, overflow=10, timeout=30)
  blocks 30s on checkout. SQLAlchemyUserRepository.get_by_email catches the
  resulting SQLAlchemyError → returns None → AuthService.login raises
  InvalidCredentialsError → 401. Reproducer: in-venv harness called
  Container().auth_service() 17×; iter 1-15 ~0ms, iter 16 = exactly 30.00s
  with QueuePool limit reached.
created: 2026-05-02
updated: 2026-05-02
---

# Debug Session: sqlalchemy-session-pool-leak

## Symptoms

- **Expected:** Wrong-password POST /auth/login returns 401 within ~200ms
  with "Invalid email or password" inline. Correct-credential POST returns
  200 within ~300ms. Subsequent requests on the same uvicorn process work
  normally.
- **Actual:** First ~15 requests succeed in <50ms each. From request 16
  onward, every dependency-resolution call into a leaky provider blocks
  exactly 30.00s (QueuePool checkout timeout) before raising
  SQLAlchemyError, which `SQLAlchemyUserRepository.get_by_email` swallows
  to `None`, which `AuthService.login` converts to
  `InvalidCredentialsError` → 401 with body
  `{"error":{"message":"Invalid email or password.",...}}`. User
  experiences a frozen 30s spinner then a misleading credentials error.
- **Errors:** None surfaced. The leak is silent because
  `SQLAlchemyUserRepository.get_by_email` catches `SQLAlchemyError` and
  returns `None` rather than re-raising. The 30s timeout never reaches the
  HTTP layer as a 5xx — it manifests as a deceptive 401.
- **Timeline:** Latent since Phase 11 (auth services introduced).
  Triggered visibly during this session because frontend hot-reload + boot
  probes ran > 15 dependency resolutions on a single uvicorn process.
- **Reproduction:**
  1. Cold-start uvicorn.
  2. Hit any endpoint depending on get_auth_service / get_key_service /
     get_rate_limit_service (or any other leaky factory provider) 16
     times.
  3. The 16th request blocks for exactly 30.00s.
  4. With auth, the 16th /auth/login returns 401 regardless of credentials.

## Evidence

- timestamp: 2026-05-02 (user diagnosis — definitive)
  source: in-venv harness invoking Container().auth_service() 17×
  observation: iterations 1-15 ~0ms each; iteration 16 = exactly 30.00s
  with QueuePool limit (size=5, overflow=10) reached, connection timed
  out. Confirms session leak from auth_service factory chain.

- timestamp: 2026-05-02
  source: app/api/dependencies.py:223-248
  observation: get_csrf_service / get_key_service / get_auth_service /
  get_rate_limit_service all use bare `return _container.X()` — no
  generator semantics, no finally close. FastAPI cannot manage the
  lifecycle of a non-generator dependency.

- timestamp: 2026-05-02
  source: app/api/dependencies.py (full file scan)
  observation: BROADER scope than user flagged — get_task_repository,
  get_task_management_service, get_scoped_task_repository,
  get_scoped_task_management_service, get_free_tier_gate, and
  get_usage_event_writer also yield without `finally session.close()`.
  Every Factory provider that wraps a session leaks. Auth path leaks
  fastest because auth runs before rate-limit/etc.

- timestamp: 2026-05-02
  source: app/core/container.py + repository __init__ signatures
  observation: All sqlalchemy_*_repository classes expose `self.session`
  (consistent attribute name). All wrapped services expose
  `self.repository` (KeyService, RateLimitService) or
  `self.user_repository` (AuthService). FreeTierGate exposes
  `self.rate_limit_service`. UsageEventWriter exposes `self.session`
  directly. Session can be closed via known accessor paths.

- timestamp: 2026-05-02
  source: app/services/auth/csrf_service.py + container.py:125
  observation: CsrfService is a Singleton with no DB session — does NOT
  leak. User diagnosis included it but it is safe as-is. Will leave
  get_csrf_service unchanged.

- timestamp: 2026-05-02
  source: app/infrastructure/database/connection.py:29
  observation: engine = create_engine(DB_URL, ...) — no pool args, so
  defaults apply: QueuePool(pool_size=5, max_overflow=10, timeout=30).
  Confirms exactly 15 connections + 30s wait matches reproducer.

## Eliminated Hypotheses

1. ~~Frontend bug~~ — RedirectIfAuthed/AuthHydratingFallback/etc. fixes
   were correct in isolation but did not address the wire-level 30s
   stall. Backend is the source.
2. ~~argon2-cffi cost~~ — successful verify is 40ms; the 30s is
   QueuePool timeout, not crypto.
3. ~~slowapi rate-limiting~~ — slowapi 429 returns instantly; the 30s
   stall happens before any rate-limit decision.
4. ~~InvalidCredentialsError handler chain slowness~~ — handler is
   <1ms; the 30s is upstream in dependency resolution.

## Resolution

- **root_cause:** SQLAlchemy Session leak across every Factory-pattern DI
  provider in `app/api/dependencies.py` that wrapped a session-bound
  repository or service. Affected providers (lines pre-fix):
    - `get_auth_service` (237) — `return _container.auth_service()` — leaks
      via `auth_service.user_repository.session`
    - `get_key_service` (230) — same pattern, leaks via
      `key_service.repository.session`
    - `get_rate_limit_service` (244) — leaks via
      `rate_limit_service.repository.session`
    - `get_task_repository` (38) — `yield` without `finally
      session.close()` — leaks via `task_repository.session`
    - `get_task_management_service` (77) — same pattern, leaks via
      `service.repository.session`
    - `get_scoped_task_repository` (283) — `finally` cleared scope but
      did not close session, leaks via `repository.session`
    - `get_scoped_task_management_service` (304) — same as above
    - `get_free_tier_gate` (350) — leaks via
      `gate.rate_limit_service.repository.session`
    - `get_usage_event_writer` (358) — leaks via `writer.session`
  CsrfService (Singleton, no session) and ML services (Singletons, no
  session) were not affected.

  Each request leaks one connection. Default `QueuePool(size=5,
  overflow=10, timeout=30)` allows 15 outstanding checkouts; the 16th
  blocks 30s on `pool.checkout()` then raises
  `sqlalchemy.exc.TimeoutError`. The downstream
  `SQLAlchemyUserRepository.get_by_email` catches `SQLAlchemyError` and
  returns `None`. `AuthService.login` interprets `None` as "user not
  found" and raises `InvalidCredentialsError` → HTTP 401 with the
  generic "Invalid email or password" body. The user observes a frozen
  30 s spinner followed by a misleading credentials error even when the
  password is correct.

  Prior frontend fixes (RedirectIfAuthed, AuthHydratingFallback,
  suppress401Redirect, 8s boot-probe timeout) were correct in their own
  scope but addressed symptoms, not the connection-pool starvation.

- **fix:** Converted every leaky provider to the
  `yield service` + `try/finally service.<...>.session.close()` pattern.
  Plain-`return` providers (`get_auth_service`, `get_key_service`,
  `get_rate_limit_service`) had their signatures changed from
  `-> Service` to `-> Generator[Service, None, None]`; FastAPI's
  `Depends(...)` accepts both forms transparently so no consumer code
  needed updating. `get_csrf_service` left as plain `return` (Singleton,
  no session). Each docstring updated to explain *why* the finally is
  load-bearing (so a future reader does not "simplify" it away).

- **verification:**
  1. `scripts/verify_session_leak_fix.py` drives every leaky provider 30
     × through the FastAPI generator-dependency lifecycle. Pre-fix this
     hangs at iter 16 for 30 s. Post-fix every iter is <1 ms — the pool
     reuses connections cleanly because `finally session.close()`
     returns each connection promptly.
  2. `pytest tests/integration/ tests/unit/api/` (excluding pre-existing
     unrelated failures: `test_task_lifecycle.py` missing `factory`
     module; flaky slowapi rate-limit cross-test pollution) →
     **187 passed**.
  3. Auth-specific suites
     (`test_auth_routes.py`, `test_per_user_scoping.py`, all
     `tests/unit/services/auth/`) → **57 passed**.

- **files_changed:**
    - `app/api/dependencies.py` — all leaky providers converted to
      `yield + finally session.close()`.
    - `scripts/verify_session_leak_fix.py` — reproducer / regression
      sentinel for the pool exhaustion.

## Current Focus

- **status:** resolved
- **hypothesis:** confirmed
- **next_action:** none (session closed)
