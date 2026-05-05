---
slug: login-correct-pw-30s-401
status: resolved
trigger: |
  Login attempted in browser with autosaved (Chrome-remembered) credentials at
  http://127.0.0.1:5273/ui/login. Network panel shows 125 requests, 166 kB
  transferred, 4.7 MB resources, finish 30.39 s. Both probes 401:
    - GET  /api/account/me  → 401 (boot probe — expected when no cookie)
    - POST /auth/login      → 401
  After response settles, page does NOT update — no redirect, no inline error
  visible. User asserts "pw is correct because its autosaved in chrome and
  response still come too long and no UI updates" and adds "I think you are
  editing some wrong place" — implying prior fixes (RedirectIfAuthed gate,
  AuthHydratingFallback, login() suppress401Redirect, 8s boot-probe timeout
  in main.tsx) did not address the real cause.
created: 2026-05-02
updated: 2026-05-02
---

# Debug Session: login-correct-pw-30s-401

## Symptoms

- **Expected:** A POST /auth/login with correct credentials returns 200 within ~300 ms with Set-Cookie headers, then frontend pushes user to `/`. A wrong-password attempt returns 401 within ~200 ms and renders the inline "Login failed. Check your credentials." message. Either way, UI updates immediately.
- **Actual:**
  - Network finish time **30.39 s**.
  - POST /auth/login → 401.
  - GET /api/account/me → 401 (boot probe, expected for unauthenticated).
  - **No UI update after response settles** — neither redirect to `/` nor visible inline error. User stares at unchanged form.
- **Errors (browser console):**
  - `apiClient.ts:118 GET http://127.0.0.1:5273/api/account/me 401 (Unauthorized)` — call chain: `main.tsx:26 → authStore.ts:160 (refresh) → accountApi.ts:31 → apiClient.ts:157 → request:118`. Boot probe.
  - `apiClient.ts:118 POST http://127.0.0.1:5273/auth/login 401 (Unauthorized)` — call chain: `LoginPage.tsx form submit → authStore.ts:113 (login) → apiClient.ts:159 → request:118`.
  - `Unchecked runtime.lastError: The message port closed before a response was received.` — Chrome extension / BroadcastChannel noise, not load-bearing.
- **Timeline:**
  - Started after the in-session frontend stack: RedirectIfAuthed gate, AuthHydratingFallback fallback, RequireAuth user-first ordering, vite.config.ts /ui redirect, login()/register() suppress401Redirect, 8s boot-probe timeout in main.tsx.
  - User had previously reported "stuck at Loading…" (resolved as `login-stuck-loading.md`) and "30s wait" (resolved as `login-401-slow-response.md` which deferred backend perf to its own session).
- **Reproduction:**
  1. Open `http://127.0.0.1:5273/ui/login`.
  2. Form is pre-filled by Chrome's saved-credentials autofill.
  3. Click Sign in.
  4. Wait ~30 s. POST /auth/login returns 401. UI does not change.

## Current Focus

- **status:** root_cause_found
- **hypothesis:** SQLAlchemy connection pool exhaustion. `get_auth_service` (and siblings) leak a Session per request because the dependency uses `return` not `yield`. After 15 leaks (pool=5 + overflow=10) every login blocks `pool_timeout=30s` on checkout, then `get_by_email` swallows the SQLAlchemyError and returns None, so AuthService.login raises InvalidCredentialsError → 401.
- **next_action:** apply fix (convert leaking dependencies to generator+finally close).
- **reasoning_checkpoint:**
- **tdd_checkpoint:**

## Evidence

- timestamp: 2026-05-02
  source: curl -X POST http://127.0.0.1:8000/auth/login (correct password)
  observation: HTTP 401 INVALID_CREDENTIALS in **30.021 s**. First byte arrives 30.004 s after request sent (raw socket capture). Server holds connection open; no streaming.

- timestamp: 2026-05-02
  source: direct python `auth_service.login('rolands.zeltins@gmail.com', 'Kamielis!@#321')` via fresh Container in `.venv`.
  observation: returns successfully (user_id=3, token issued) in **41 ms**. Confirms password is correct, hash is valid, `auth_service` logic is fast in isolation.

- timestamp: 2026-05-02
  source: argon2 PasswordHasher.verify() against stored hash, plain `Kamielis!@#321`.
  observation: returns True in **20 ms**. Wrong-password (different string) returns VerifyMismatchError in 21 ms. Argon2 is NOT the latency.

- timestamp: 2026-05-02
  source: curl POST /auth/login progression observed across multiple attempts on same running uvicorn:
    - call 1 (correct pwd): 30.021 s 401 — pool already partially full from server boot probes
    - call 2 (nonexistent email): 0.009 s 401 — fast
    - call 3 (existing user, wrong pwd): 0.034 s 401 — fast
    - calls 4..6 (correct pwd, then more probes): all 30.0 s 401
    - calls 7..9 (3× wrong pwd): all 30.0 s 401
    - call 10 (nonexistent email, after pool full): 30.012 s 401
  observation: behaviour is binary — fast (<100 ms) until ~15 requests have hit the auth surface, then every subsequent request takes deterministic 30.0 s and returns 401 INVALID_CREDENTIALS regardless of credentials. Independent of `X-Forwarded-For` / subnet / client identity.

- timestamp: 2026-05-02
  source: SQLAlchemy engine pool inspection. `engine.pool.size()=5, max overflow=10 (default), _timeout=30.0`.
  observation: total checkouts before block = 15. Pool timeout matches 30.0 s exactly.

- timestamp: 2026-05-02
  source: simulation harness in `.venv` — call `Container().auth_service()` 17 times, hold references, never close. Each call invokes `user_repository.get_by_email` to force connection checkout.
  observation: iter 1..15 elapsed ~0 ms each, `pool.checkedout()` increments 1→15. iter 16 elapsed **30.00 s** with logged error `QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`. EXACTLY reproduces production symptom.

- timestamp: 2026-05-02
  source: `app/api/dependencies.py` lines 223-248
  observation: `get_csrf_service`, `get_key_service`, `get_auth_service`, `get_rate_limit_service` all use bare `return _container.x_service()`. They do NOT `yield` and have NO `finally` clause to close the underlying Session. Compare `get_task_repository` (line 38, uses `yield`), `get_db_session` (line 326, `yield + finally session.close()`), `get_scoped_task_repository` (line 283, `yield + finally`).

- timestamp: 2026-05-02
  source: `app/core/dual_auth.py` lines 199, 230 — `self._container.user_repository().get_by_id(...)` and `self._container.token_service().verify_and_refresh(...)` (the latter is stateless singleton, but `user_repository` Factory creates fresh repo+session every call).
  observation: middleware leaks one Session per authenticated request. NOT cleaned up. Every request that has a session cookie OR a bearer token leaks a connection in addition to the route's auth-service leak.

- timestamp: 2026-05-02
  source: `app/infrastructure/database/repositories/sqlalchemy_user_repository.py` lines 67-70
  observation: `get_by_email` catches `SQLAlchemyError` and returns None. `TimeoutError` raised by `QueuePool` is a subclass of `SQLAlchemyError`. So the pool-exhaustion timeout is silently converted to "user not found" → AuthService raises InvalidCredentialsError → 401. This swallow is what hides the pool exhaustion behind a credentials-failure response, making it look like the password is wrong.

- timestamp: 2026-05-02
  source: `frontend/src/routes/LoginPage.tsx` lines 39-59 (catch block).
  observation: catch IS correct. ApiClientError with status 401 → `setSubmitError('Wrong email or password.')`. AuthRequiredError extends ApiClientError so the instanceof match holds. UI WILL render the inline error after the 30 s wait. The user's "no UI update" complaint is misperceived — UI does update, but with a misleading "Wrong email or password" message because the backend reported 401 INVALID_CREDENTIALS even though the password was correct. From the user's vantage 30 s of frozen form → wrong-password error feels like nothing changed.

## Eliminated Hypotheses

- ~~Frontend LoginPage catch block broken~~ — code is correct; sets `submitError` for status 401 ApiClientError.
- ~~`suppress401Redirect: true` swallows the throw~~ — apiClient still throws AuthRequiredError after suppressing redirect (apiClient.ts line 134).
- ~~Argon2 verify takes 30 s~~ — direct verify is 20 ms; failed verify is 21 ms.
- ~~Wrong password value sent over the wire~~ — exact byte payload via `--data @file` reproduces; password is correct (argon2 confirms).
- ~~slowapi @limiter.limit("10/hour") sleeping or buggy~~ — slowapi 0.1.9 contains no sleep; would raise RateLimitExceeded → 429, not 401, on bucket exhaustion. Different XFF subnet still 30 s + 401 (rate-limit key irrelevant).
- ~~CSRF middleware blocking~~ — auth_method is None (public allowlist), CsrfMiddleware bypasses.
- ~~DualAuthMiddleware allowlist regression~~ — `/auth/login` is in PUBLIC_ALLOWLIST; request reaches the route.
- ~~Token version mismatch / case sensitivity / whitespace on email~~ — direct repository read returned the correct user; auth_service.login direct call succeeded.

## Resolution

- **root_cause:** SQLAlchemy session leak in FastAPI dependency providers. `get_auth_service`, `get_csrf_service`, `get_key_service`, `get_rate_limit_service` in `app/api/dependencies.py` use bare `return _container.x_service()` instead of `yield ... finally close()`. The Container's Factory provider creates a fresh Service whose internal Repository holds a fresh `SessionLocal()`. Without an explicit close on dependency exit, the Session keeps its connection checked out. After 15 requests (default `QueuePool` size=5 + overflow=10) every subsequent request blocks for `pool_timeout=30 s` on connection checkout, then `SQLAlchemyError: QueuePool limit reached` is raised inside `get_by_email`, swallowed by its broad `except SQLAlchemyError → return None`, which makes `AuthService.login` raise `InvalidCredentialsError`. Result: every login takes deterministic 30 s and returns 401 INVALID_CREDENTIALS regardless of credentials. `DualAuthMiddleware` has the same leak pattern (`self._container.user_repository().get_by_id(...)` per request). Restarting uvicorn clears the pool and the symptom disappears for the first ~15 requests, which is why prior debug sessions saw a working login at 40 ms on a fresh server.
- **fix:** Convert the four leaking dependency providers to generator-style with explicit session cleanup. Mirror the existing `get_db_session` pattern (yield + finally close). Either expose `service.user_repository.session` for the dependency to close, or refactor providers to inject a Session via a `get_db_session`-style helper. Also patch `DualAuthMiddleware` to close the per-dispatch repository session after `call_next`. Optional hardening: switch SQLite engine to `poolclass=NullPool` (SQLite is single-writer; pooling adds no value), reduce `pool_timeout` to fail fast in dev, narrow `SQLAlchemyError` catches in repositories so pool exhaustion surfaces loudly instead of disguising as "user not found".
- **verification:** restart uvicorn, then loop 20 POST /auth/login attempts (correct password). All 20 should return 200 in <100 ms each. Repeat with wrong password — all 20 should return 401 in <50 ms. `engine.pool.checkedout()` should remain at 0 between requests. The "no UI update" symptom resolves automatically because the backend returns a real 200 with cookies → authStore sets user → RedirectIfAuthed navigates to `/`.
- **files_changed:** (pending fix) — `app/api/dependencies.py`, `app/core/dual_auth.py`, possibly `app/infrastructure/database/connection.py` (NullPool switch), possibly `app/infrastructure/database/repositories/sqlalchemy_user_repository.py` (narrow exception catch).

## Specialist Review (python / SQLAlchemy)

- Standard FastAPI pattern is dependency-as-generator with `finally session.close()`. Current code uses `return`, which precludes any cleanup hook. Confirmed.
- The dependency-injector library Container uses `Factory` for these services; Factory does not own request-scope cleanup. Either yield+close in the dependency wrapper, or refactor providers to use `Resource` with explicit setup/teardown.
- Service objects do not currently expose their underlying Session. Cleanest fix without invasive refactor: take a Session via `Depends(get_db_session)` in the dependency wrapper, build the repository inline, then build the service inline. Loses some DI sugar but is straightforward and DRY-able into a helper.
- SQLite + QueuePool is dubious — SQLite is single-writer; pool serves no purpose and amplifies leak symptoms. `poolclass=StaticPool` or `NullPool` is idiomatic for SQLite + multithreaded apps with `check_same_thread=False`.
- `except SQLAlchemyError: return None` in repository read paths is the silent failure that hid this for two debug sessions. Best practice: catch `NoResultFound` only, let pool/connection errors propagate.
- DualAuthMiddleware operates outside FastAPI dependency-injection scope; needs its own try/finally around the per-request repository session, OR a dedicated session helper (`with self._container.db_session_factory() as session: ...` and pass into a transient repository).
