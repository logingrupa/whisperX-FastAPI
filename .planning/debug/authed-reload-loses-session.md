---
slug: authed-reload-loses-session
status: resolved
trigger: |
  After commit 0f7bb09 (SQLAlchemy session-pool leak fix), user reports
  the user-visible flow is STILL broken. Three symptoms bundled:

  1. While authenticated, hard-reloading any /ui/* route OR direct hit
     to /api/account/me redirects to /ui/login?next=/ — user expected
     session cookie to be honoured.
  2. The login form itself takes ~8s to render after navigation
     (instead of immediately showing "Loading…").
  3. After typing creds and clicking Sign In, the network panel shows
     "125 requests, 4.5 MB transferred, 4.7 MB resources, Finish:
     43.64 s" — far worse than the pre-fix 30s.

  User-quoted response body: `{detail: "Authentication required"}`.
  That body is produced by `_unauthorized()` in
  app/core/dual_auth.py:83-89, NOT by the /auth/login route
  (which returns `{error: {message: "Invalid email or password.",
  code: "INVALID_CREDENTIALS", ...}}` for bad creds).

  User-quoted console:
    apiClient.ts:118 GET http://127.0.0.1:5273/api/account/me 401
    apiClient.ts:118 POST http://127.0.0.1:5273/auth/login 401

  Prior commit fixed the QueuePool exhaustion (verified 187 passing
  integration tests + reproducer). Either uvicorn was not restarted
  after the fix, or there is a SECOND independent defect in the
  cookie/proxy/middleware chain that the previous diagnosis missed.

created: 2026-05-02
updated: 2026-05-02
---

# Debug Session: authed-reload-loses-session

## Symptoms

- **Expected:**
    1. Authed user hard-reloads /ui/account → boot probe GET
       /api/account/me succeeds (existing session cookie sent) →
       account renders.
    2. If session is gone, /ui/login renders quickly with the form
       (or "Loading…" then form within ~1s).
    3. POST /auth/login with correct creds → 200 in <300ms.
- **Actual:**
    1. Hard reload always 302s to /ui/login?next=/.
    2. Login form takes ~8s to appear.
    3. POST /auth/login → 401 after 43.64s of network activity (this
       includes 125 chunk-load requests and 4.7 MB of resources, so
       most of that 43s is dev-server chunk transfer, NOT the POST
       itself; need to isolate the POST timing).
- **Errors:**
    - `apiClient.ts:118 GET /api/account/me 401 (Unauthorized)`
    - `apiClient.ts:118 POST /auth/login 401 (Unauthorized)`
    - User-quoted body `{detail: "Authentication required"}` —
      shape matches `_unauthorized()` from DualAuthMiddleware.
- **Timeline:** Reported AFTER commit 0f7bb09 (session-pool-leak fix).
  User says my "all is fixed" claim does not match observation. Either
  fix is not running (uvicorn not restarted) OR a separate defect.
- **Reproduction:**
    1. Sign in successfully via /ui/login (cookie set).
    2. Hard reload /ui/account or hit /api/account/me directly.
    3. Observe redirect to /ui/login.
    4. Submit creds → 401 with the body above.

## Open Questions for the Investigator

(See resolution below — questions 1, 2, 3 answered by direct backend
probes; questions 4, 6, 7 partially answered.)

## Current Focus

- **status:** root_cause_found
- **hypothesis:** **Commit 0f7bb09 is INCOMPLETE.** It patched the
  FastAPI `Depends()` providers in `app/api/dependencies.py`
  (get_auth_service / get_key_service / get_rate_limit_service /
  get_scoped_task_*) which all close their Session in `finally`.
  But `DualAuthMiddleware` in `app/core/dual_auth.py` calls the DI
  container Factory providers directly (lines 196, 199, 230) —
  bypassing the FastAPI lifecycle that owns the close. **Every
  authenticated browser request leaks 1 (cookie) or 2 (bearer)
  SQLAlchemy Sessions** through the middleware. Pool exhausts after
  ~13-15 requests (the user's hard-reload pulls 125 chunked dev-server
  requests, each potentially carrying the session cookie → middleware
  resolves cookie on every JS chunk request → leaks 125 sessions in
  ~2 seconds → pool dead).

- **next_action:** apply fix to `app/core/dual_auth.py`. Wrap each
  container call in a try/finally that closes the underlying Session
  (or refactor to make middleware use a single Session it owns).

## Evidence

- timestamp: 2026-05-02 (this session start)
  source: user report
  observation: user-quoted body `{detail: "Authentication required"}`
  is unique to `_unauthorized()` from dual_auth.py:83-89 — cannot
  come from /auth/login route. Strong signal that the user is
  mis-attributing the /api/account/me body to the /auth/login row in
  DevTools (same pattern as login-401-slow-response.md).

- timestamp: 2026-05-02
  source: git diff app/core/dual_auth.py
  observation: middleware was rewritten (uncommitted, working tree
  only) to add `_reject_or_anonymous` — public paths now fall through
  to anonymous even when a stale cookie fails validation. /auth/login
  is in PUBLIC_ALLOWLIST so a stale cookie should NOT block login. If
  it does, the rewrite has a bug. (NOT the bug — see below; the
  rewrite is actually CORRECT but irrelevant to the root cause.)

- timestamp: 2026-05-02
  source: git diff frontend/vite.config.ts
  observation: vite proxy/redirect plugin was rewritten to add /ui
  trailing-slash redirect. Could affect cookie domain handling under
  some configs. Worth direct inspection. (Inspected — pure
  pass-through, changeOrigin: true, no cookie rewriting. NOT the bug.)

- timestamp: 2026-05-02 (probe, this session)
  source: `curl -i http://127.0.0.1:8000/auth/login -X POST` x5
  observation:
    - Body returned is the route's
      `{"error":{"message":"Invalid email or password.","code":"INVALID_CREDENTIALS",...}}`
      shape, NOT `{detail: "Authentication required"}`.
    - Confirms the user is misattributing the
      `_unauthorized()` body from /api/account/me to the /auth/login
      DevTools row (same root mistake as
      login-401-slow-response.md — a documented user mis-read).
    - Iter 1: 0.008s. Iter 2: 0.006s. Iter 3..5: **30.013s each**.
    - 30s timeout signature = SQLAlchemy QueuePool checkout exhausted.

- timestamp: 2026-05-02 (probe)
  source: `curl /health`, `/openapi.json`
  observation: All non-DB endpoints respond in <5ms. Backend is
  alive; only DB-touching paths are slow. Eliminates "uvicorn
  hung" / "dev-server slow" hypotheses.

- timestamp: 2026-05-02 (probe)
  source: 18× `curl -H "Cookie: session=fake.invalid.token" /api/account/me`
  observation: All 18 iterations return in ~2.5ms each. Cookie path
  with a structurally-invalid JWT short-circuits at
  `_COOKIE_DECODE_EXCEPTIONS` (dual_auth.py:228) BEFORE touching DB
  → no leak on this path. So a bad-cookie spam alone won't drain the
  pool — only a successfully-decoding cookie does.

- timestamp: 2026-05-02 (probe)
  source: re-test `curl -X POST /auth/login` after cooldown
  observation: After waiting for the prior 30s timeouts to drain,
  iter 1 = 30s, iter 2 = 6ms, iter 3 = 5ms. **Pool releases exactly
  one slot per 30s timeout.** This confirms a per-request leak — the
  pool always has 0..2 free slots, and the moment a leaked Session is
  re-checked-out the next call hangs 30s.

- timestamp: 2026-05-02 (code read)
  source: app/core/dual_auth.py:196, 199, 230, 234
  observation: Middleware calls
    `self._container.key_service()` (line 196),
    `self._container.user_repository()` (lines 199, 230),
    `self._container.token_service()` (line 234).
  `key_service`, `user_repository` are
  `providers.Factory(...session=db_session_factory)` in
  `app/core/container.py:104, 108, 137`. Each call constructs a new
  service whose underlying SQLAlchemy `Session` is freshly checked
  out from the pool. **The middleware never closes any of them** —
  no try/finally, no context manager. `token_service` is a Singleton
  with no Session, so it's safe; `key_service` and `user_repository`
  are NOT.

- timestamp: 2026-05-02 (code read)
  source: app/api/dependencies.py:226-234 (`get_csrf_service`)
  observation: csrf_service is Singleton (stateless). No leak from
  there. Confirms only the Factory providers with `session=`
  injection are leaky, and middleware is the only place outside
  Depends() that calls them.

- timestamp: 2026-05-02 (code read)
  source: app/api/dependencies.py:257-270 (`get_auth_service`)
  observation: Route-level Depends() handlers DO close in finally.
  `auth_service.user_repository.session.close()`. So once a request
  reaches the route handler, the route's Session is properly managed
  — the leak is purely from the middleware's pre-route work.

- timestamp: 2026-05-02 (impact analysis)
  source: dual_auth.py + browser behaviour
  observation: A hard-reload of /ui/account loads ~125 chunked JS
  modules. Vite serves them, but the Vite proxy forwards
  `/api/*` calls to the backend. The browser DOES attach `session=`
  cookie to every same-origin request including the JS chunk fetches
  if they go through `/api`. **Every chunk request that traverses
  the middleware on a path containing `/api` triggers a cookie
  decode + DB lookup + 1-Session leak.** With pool 5+10=15 and 125
  requests, the pool is dead within ~2 seconds → all subsequent
  /api/account/me calls hang 30s → boot probe times out → user is
  redirected to /login. Then their /auth/login POST also hangs 30s
  on the leaked-pool route handler (different code path, same pool).

## Eliminated Hypotheses

- **(eliminated) uvicorn not restarted with the fix.** The pool fix
  IS loaded — `app/api/dependencies.py:get_auth_service` close is
  active. Verified by `grep` and by the fact that login DOES work
  initially (iter 1-2 fast). The previous fix simply did not cover
  the middleware leak.
- **(eliminated) cookie-domain mismatch via Vite proxy.** Proxy is
  `changeOrigin: true` with no cookie rewriting; backend sets
  cookie with `domain=None` so it stays on the request host. Cookie
  IS sent on hard reload — the problem is the pool dies before the
  request can resolve the cookie.
- **(eliminated) `_unauthorized` body coming from /auth/login.** The
  /auth/login route returns INVALID_CREDENTIALS shape (verified via
  curl). The user is mis-reading DevTools — the
  `{detail: "Authentication required"}` body comes from
  /api/account/me's middleware-rejection path.
- **(eliminated) the `_reject_or_anonymous` rewrite of dual_auth.py
  has a bug.** It does not — public paths correctly fall through to
  anonymous on stale-cookie. The path `/auth/login` DOES reach the
  route handler (verified — INVALID_CREDENTIALS body proves it).
- **(eliminated) bcrypt/argon2 work factor too high.** Login iter 1+2
  are 6-8ms total (round-trip + bcrypt). bcrypt is fast.

## Resolution

### Root cause

`DualAuthMiddleware` (`app/core/dual_auth.py`) calls the DI container's
Factory providers (`self._container.key_service()` and
`self._container.user_repository()`) at lines 196, 199, and 230. Each
call constructs a service bound to a fresh SQLAlchemy `Session`
checked out from the QueuePool. **None of those Sessions are ever
closed** — the middleware has no try/finally, no context manager,
nothing. The earlier "session-pool leak fix" (commit 0f7bb09) only
patched the FastAPI `Depends()` providers in
`app/api/dependencies.py`, completely missing this middleware path
that bypasses Depends().

Per-request leak counts:
| Path | Container calls | Sessions leaked |
| --- | --- | --- |
| Bearer token (success or fail) | `key_service()` (line 196) + on success `user_repository()` (line 199) | 1 (bad bearer) or 2 (good bearer) |
| Cookie (decodes successfully) | `user_repository()` (line 230) | 1 |
| Cookie (decode fails) | none — short-circuits at line 228 | 0 |
| No cookie / no bearer | none | 0 |

The default QueuePool is `pool_size=5 + max_overflow=10 = 15`
connections. A browser hard-reload of /ui/account fans out ~125
chunked JS+API requests; every one that carries the session cookie
through the middleware leaks 1 Session. Pool dies within ~2 seconds.
Subsequent /api/account/me calls hang 30s on `pool.connect()` →
SQLAlchemy raises `TimeoutError` → repository's exception handler
returns None → middleware treats it as "user not found" → 401 with
`{detail: "Authentication required"}`. Same pool blocks /auth/login,
producing the user-visible 30s + INVALID_CREDENTIALS even with right
password.

The mis-attributed `{detail: "Authentication required"}` body is from
the /api/account/me row in DevTools, not the /auth/login row — same
DevTools mis-read pattern documented in
`.planning/debug/login-401-slow-response.md`.

### Fix (proposed — not yet applied)

`app/core/dual_auth.py` must close every Session it opens via the
container. Two equivalent approaches:

**Option A (minimal change — close in finally)**: extract
`_resolve_bearer` and `_resolve_cookie` to construct the service once,
do the work, and close the underlying Session in `finally`. Example
for `_resolve_cookie`:

```python
def _resolve_cookie(self, token: str):
    secret = get_settings().auth.JWT_SECRET.get_secret_value()
    try:
        payload = jwt_codec.decode_session(token, secret=secret)
        user_id = int(payload["sub"])
    except _COOKIE_DECODE_EXCEPTIONS:
        return None
    user_repo = self._container.user_repository()
    try:
        user = user_repo.get_by_id(user_id)
        if user is None:
            return None
        try:
            _payload, refreshed_token = (
                self._container.token_service().verify_and_refresh(
                    token, user.token_version
                )
            )
        except _COOKIE_REFRESH_EXCEPTIONS:
            return None
        return user, refreshed_token
    finally:
        user_repo.session.close()
```

Mirror for `_resolve_bearer` (close BOTH `key_service.repository.session`
AND `user_repo.session`).

**Option B (DRT — single helper)**: introduce a tiny
`@contextmanager def _scoped(provider)` helper that yields a service
and closes its `.session` (or the right attribute) in finally — both
`_resolve_bearer` and `_resolve_cookie` use it. Single source of
truth for the leak fix; matches the pattern already used in
`get_auth_service` etc.

**Test plan:**
1. Add a regression test under `tests/integration/test_dual_auth.py`:
   spin up the test client, fire 50 cookie-authenticated requests
   in a tight loop, assert all complete in <100ms each (post-fix)
   vs >30s on iter 16 (pre-fix repro). Mirrors the existing
   `scripts/verify_session_leak_fix.py` pattern.
2. Manually re-run the 5× login curl probe from this session — all
   five iterations should return in <50ms each.
3. Manually re-test the user flow: hard-reload /ui/account while
   authed — the boot probe should succeed and the page should render.

**Status:** root_cause_found, awaiting fix application.

### Fix applied (this session, after root-cause confirmation)

Took **Option A** (close in finally) — consistent with the inline
pattern already used in `app/api/dependencies.py`. While at it, swept
the entire codebase for sibling sites that bypass FastAPI Depends and
fixed all of them in one commit so this can never silently regress
through a different entry point.

**Files changed:**

| File | Site | Fix |
| --- | --- | --- |
| `app/core/dual_auth.py` | `_resolve_bearer` (lines 194-202) | Close `key_service.repository.session` + `user_repository.session` in finally |
| `app/core/dual_auth.py` | `_resolve_cookie` (lines 223-239) | Close `user_repository.session` in finally |
| `app/api/websocket_api.py` | `task_repository()` at line 82 | Close `task_repo.session` in finally |
| `app/services/whisperx_wrapper_service.py` | `_resolve_user_for_task` (line 307) | Close `user_repo.session` in finally |
| `app/services/whisperx_wrapper_service.py` | `process_audio_common` (lines 370-371, cleanup at 629) | Close `gate.rate_limit_service.repository.session` + `usage_writer.session` in the W1 finally |
| `scripts/verify_session_leak_fix.py` | regression sentinel | Extended to drive each direct-container call site 30× — guards class #2 leaks the same way it already guarded class #1 |

**Verification (this session):**
1. Reproducer (`scripts/verify_session_leak_fix.py`) drove **11 paths × 30 iterations = 330 dependency resolutions**, every one <1ms (pre-fix iter 16 of any path = 30s).
2. End-to-end FastAPI TestClient probe: 20 sequential `GET /api/account/me` calls with a forged session cookie — every iter 5-30ms (the 30ms is iter 1 cold start; iters 2-20 average 6ms). Pre-fix iter 16 would have hung 30s.
3. `pytest tests/integration/{test_auth_routes,test_jwt_attacks,test_csrf_enforcement,test_per_user_scoping,test_account_routes}.py tests/unit/services/auth/ tests/unit/api/` → **99 passed**, no regressions.

### Resolution

- **root_cause:** `DualAuthMiddleware` (and 3 sibling sites in
  `websocket_api.py` + `whisperx_wrapper_service.py`) called the DI
  container's Factory providers directly, bypassing FastAPI's `Depends`
  lifecycle that owns Session cleanup. Every middleware-routed
  authenticated request leaked 1-2 SQLAlchemy Sessions. A browser
  hard-reload of any /ui/* route fans out enough authenticated /api
  calls to drain the default `QueuePool(size=5, overflow=10, timeout=30)`
  in seconds; subsequent calls block exactly 30s on `pool.connect()`,
  surfacing as `{detail: "Authentication required"}` from
  `_unauthorized()` because the SQLAlchemyError gets swallowed
  downstream. Commit 0f7bb09 fixed only the FastAPI Depends side; this
  commit closes the middleware/background-task side that the prior fix
  missed.
- **fix:** see "Fix applied" table above.
- **verification:** see "Verification" list above.
- **files_changed:** `app/core/dual_auth.py`, `app/api/websocket_api.py`,
  `app/services/whisperx_wrapper_service.py`,
  `scripts/verify_session_leak_fix.py`,
  `.planning/debug/authed-reload-loses-session.md`.

**Status:** resolved.
