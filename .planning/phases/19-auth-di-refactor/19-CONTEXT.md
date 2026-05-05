---
phase: 19
slug: auth-di-refactor
title: "Auth + DI structural refactor — drop dependency_injector, move auth to Depends, kill AUTH_V2 flag"
status: ready-for-plan
created: 2026-05-02
supersedes_lock: 13-atomic-backend-cutover
deviation_log: .planning/DEVIATIONS.md
---

# Phase 19 — Auth + DI Structural Refactor

## Mission (one sentence)

Eliminate the architectural anti-pattern that produced two consecutive
session-leak fix commits (`0f7bb09`, `61c9d61`) by replacing the
`dependency_injector` Factory + middleware-direct-container call pattern
with native FastAPI `Depends` and module-level singletons — ZERO direct
`_container.X()` calls, ZERO manual `session.close()` boilerplate, ONE
`Session` per HTTP request, ONE auth resolution path.

## Why this work exists

Two production-impacting bugs (login 30s/401 + authed reload loses
session) were both root-caused to direct `_container.X()` calls bypassing
the FastAPI `Depends` lifecycle that owned `Session.close()`. Each fix
added inline `try/finally` instead of fixing the structure. The pattern
will keep regenerating leaks until the structure changes. User
explicitly waived the Phase 13 architectural lock and asked for "clean,
fast, working code, fresh code, best practices, industry".

The deviation from the Phase 13 lock is recorded in
`.planning/DEVIATIONS.md` (created by this phase, first entry).

## Locked architectural decisions (DO NOT delegate to planner)

These are decided **here**, in CONTEXT.md, not deferred to PLAN.md.
Verified against codebase before locking.

### D1. Drop `dependency_injector` library entirely.

**Evidence:** `grep -rn '@inject\|Provide\[\|container\.wire' app/` →
ZERO matches. The library is imported in `app/core/container.py` only;
the rest of the app uses bare `_container.X()` lookups. Migration is
mechanical text replacement — no decorator unwiring, no `wire()` graph
to untangle.

Replacement:
- Module-level singletons (stateless services with no DB):
  `PasswordService`, `CsrfService`, `TokenService`, `WsTicketService`,
  `WhisperX*Service` (ML). Define once in `app/core/services.py` (new
  module). Access via `from app.core.services import password_service`.
- `Session`-bound services: build inside `Depends` chain (see D2).

`app/core/container.py` is DELETED at end of phase. `app/main.py`
`Container()` instantiation + `dependencies.set_container(container)`
calls are deleted.

### D2. Move auth to `Depends`. Kill `DualAuthMiddleware` + `BearerAuthMiddleware`.

```python
# app/api/dependencies.py (new shape)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_user_repo(db: Session = Depends(get_db)) -> IUserRepository:
    return SQLAlchemyUserRepository(db)

# ... one Depends per repo, all chained off get_db ...

async def authenticated_user(
    request: Request, response: Response,
    db: Session = Depends(get_db),
) -> User:
    # 1) bearer wins when both presented
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return _resolve_bearer(auth[7:], db)
    # 2) cookie
    cookie = request.cookies.get("session")
    if cookie:
        return _resolve_cookie(cookie, db, request, response)
    raise HTTPException(401, "Authentication required",
                        headers={"WWW-Authenticate": 'Bearer realm="whisperx"'})

async def authenticated_user_optional(...) -> User | None:
    # Same as above, returns None instead of raising. Used by routes that
    # accept anonymous (currently none — placeholder for future).
```

- Protected route: `Depends(authenticated_user)`.
- Public route (`/auth/login`, `/auth/register`, `/health`, etc.): no
  dep. The PUBLIC_ALLOWLIST goes away — it was an inverted index of
  "routes that don't include the dep", redundant once routes opt in.
- Sliding cookie refresh: `response.set_cookie(...)` inside
  `_resolve_cookie`. **Conflict policy**: routes that return their own
  `Response` (e.g. `/auth/login`, `/auth/logout`) set cookies on that
  response and skip the slide (they don't include the dep).

### D3. Kill `AUTH_V2_ENABLED` feature flag.

V2 is THE auth path. Phase 13 cutover is done. Remove the flag, the
`is_auth_v2_enabled()` helper, both branches in `app/main.py:198-208`,
the prod fail-loud guard at `app/main.py:257-262`, and the
`BearerAuthMiddleware` legacy fallback. Single auth wiring is an
invariant of phase output.

### D4. Convert `CsrfMiddleware` to a `Depends`.

Compose with `authenticated_user` — single auth-flavor detection
codepath. `csrf_middleware.py:67` currently calls
`_container.csrf_service()` (lib coupling). New form:

```python
def csrf_protected(
    request: Request,
    user: User = Depends(authenticated_user),  # auth runs first
) -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"): return
    if request.headers.get("authorization", "").startswith("Bearer "): return
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("X-CSRF-Token")
    if not csrf_service.verify(cookie, header):
        raise HTTPException(403, "CSRF token missing or invalid")
```

Apply via `dependencies=[Depends(csrf_protected)]` on the routers that
need it. `CsrfMiddleware` class deleted.

### D5. Bearer JOIN optimization is OUT OF SCOPE for Phase 19.

Tracked separately as Phase 20. This phase preserves the existing
two-query bearer path (verify_plaintext → get_by_id) verbatim. Reason:
mixing structural refactor + perf optimization makes verification
harder; one revert button per concern.

### D6. Keep `scripts/verify_session_leak_fix.py`. Add pytest test alongside.

The script stays in the repo for one full release cycle after phase
ships. New `tests/integration/test_no_session_leak.py` runs the same
50-request loop in CI on every PR. Script deleted only when CI has been
green for 2 weeks AND the structural invariant `grep -rn '_container\.'
app/ → 0` has held.

## Files in scope (verified — every callsite enumerated)

`_container.X()` callsites the refactor must eliminate (20 total across
6 files, confirmed via `grep -rn '_container\.' app/`):

| File | Line(s) | Method called | Action |
|---|---|---|---|
| `app/api/dependencies.py` | 53, 72, 88, 116, 140, 164, 190, 234, 250, 266, 282, 334, 356, 374, 400, 416 | various | Rewrite as `Depends` chain |
| `app/api/ws_ticket_routes.py` | 57 | `ws_ticket_service()` | Module-level singleton |
| `app/api/websocket_api.py` | 81, 85 | `ws_ticket_service()`, `task_repository()` | Singleton + explicit `with SessionLocal()` |
| `app/core/csrf_middleware.py` | 67 | `csrf_service()` | Convert middleware → `Depends(csrf_protected)` |
| `app/core/dual_auth.py` | 209, 218, 262, 271 | various | DELETE FILE — replaced by `authenticated_user` dep |
| `app/services/whisperx_wrapper_service.py` | 310, 376, 377 | `user_repository()`, `free_tier_gate()`, `usage_event_writer()` | Background task: explicit `with SessionLocal() as db:` block |

Other files in scope:
- `app/main.py` — delete `Container()` instantiation, delete
  `is_auth_v2_enabled()` branches, delete `BearerAuthMiddleware`
  registration, delete prod guard.
- `app/core/container.py` — DELETE FILE.
- `app/core/services.py` — NEW FILE — module-level singletons.
- `app/api/auth_routes.py`, `account_routes.py`, `key_routes.py`,
  `billing_routes.py`, `task_api.py` — re-wire to new `Depends`.
- `app/api/dependencies.py` — full rewrite around `get_db` + chained
  `Depends`. No inline `session.close()` anywhere except `get_db`.
- `app/infrastructure/database/connection.py` — unchanged (engine,
  `SessionLocal`, FK pragma listener).
- `app/services/auth/{auth,csrf,key,rate_limit,password,token}_service.py` —
  unchanged (services themselves are correct; only their wiring changes).

## Frontend stack — DO NOT TOUCH

Verified zero-frontend-change is required. Contracts that MUST stay
byte-identical post-refactor:

- Cookie names `session` (HttpOnly) + `csrf_token` (non-HttpOnly).
- `X-CSRF-Token` header on POST/PUT/PATCH/DELETE.
- `Set-Cookie` attributes (Path, SameSite, Max-Age, Secure) — verify via
  Playwright e2e diff, not by code reading.
- 401 redirect target `/ui/login?next=<currentUrl>`.
- `/api/account/me` boot probe (200 with body, 401 without).
- All endpoint shapes: status codes + JSON bodies.

## Behaviors to preserve EXACTLY (verifiable)

- Bearer wins when both Authorization + cookie are presented.
- Cookie sliding refresh: every authed cookie request re-issues
  `Set-Cookie: session=...`.
- `token_version` invalidation: bumping `users.token_version` in DB
  rejects all old JWTs (logout-all flow).
- Bad-cookie on a public path falls through to anonymous (recovery: a
  stale cookie must NOT lock user out of `/auth/login` — explicit
  regression test required).
- CSRF check ONLY on cookie-auth state-mutating requests; bearer skips.
- Middleware 401 body shape: `{"detail":"Authentication required"}`.
- `/auth/login` 401 body shape:
  `{"error":{"message":...,"code":"INVALID_CREDENTIALS",...}}`.
- Per-user task scoping: `set_user_scope(user.id)` on every read/write
  of `tasks` table.
- `slowapi` rate limits on `/auth/login`, `/auth/register`.
- `usage_events` row written on transcribe success.
- Concurrency slot release on transcribe success AND failure (W1
  finally).
- `WsTicketService` Singleton in-memory dict survives across requests
  (Factory would silently break ticket store).

## Out of scope (DO NOT do these in Phase 19)

- Frontend changes (zero — refactor is a backend-internal restructure).
- Database schema changes / migrations.
- Bearer JOIN optimization (Phase 20).
- New endpoints.
- Switching ORM / DB / web framework.
- Phase 13 documentation rewrite (only adds DEVIATIONS.md entry).
- Removing `slowapi` / replacing rate-limit machinery.

## Verification gates (pre-merge — ALL must pass)

### Structural invariants (greppable)

1. `grep -rn '_container\.' app/` → ZERO matches. (`app/core/container.py`
   no longer exists, so this is structural.)
2. `grep -rn 'session\.close()' app/` → exactly ONE match: inside
   `get_db` in `app/api/dependencies.py`. Background tasks
   (`whisperx_wrapper_service.py`, `audio_processing_service.py`) and the
   WebSocket route (`websocket_api.py`) all use `with SessionLocal() as
   db:` blocks (context-manager close, no literal `.close()`).
3. `grep -rn 'dependency_injector' app/` → ZERO matches.
4. `grep -rn 'AUTH_V2_ENABLED\|is_auth_v2_enabled\|BearerAuthMiddleware\|DualAuthMiddleware' app/`
   → ZERO matches.

### Test inventory (no silent test loss)

5. **Baseline snapshot at phase start**:
   `.venv/Scripts/python.exe -m pytest --collect-only -q > tests/baseline_phase19.txt`
   committed in T-19-01.
6. **End-of-phase**: collected count ≥ baseline; no test name from
   baseline missing in post-refactor collection.

### Behavior gates

7. `.venv/Scripts/python.exe -m pytest tests/ --tb=short` → ALL GREEN.
8. New test `tests/integration/test_no_session_leak.py`: fires 50
   sequential authed `GET /api/account/me` calls via `TestClient`,
   asserts each completes < 100ms (pre-fix this hangs at iter ~16).
9. `scripts/verify_session_leak_fix.py` → still passes (kept per D6).

### End-to-end smoke (TestClient)

10. POST `/auth/register` → 201 + `Set-Cookie: session` +
    `Set-Cookie: csrf_token`.
11. GET `/api/account/me` with that cookie → 200.
12. POST `/auth/login` wrong creds → 401 with `INVALID_CREDENTIALS` body.
13. POST `/auth/login` right creds → 200.
14. POST `/auth/logout-all` without `X-CSRF-Token` → 403.
15. POST `/auth/logout-all` with `X-CSRF-Token` → 200.
16. Bearer GET `/api/account/me` → 200.
17. Tampered JWT cookie → 401.
18. Stale cookie + POST `/auth/login` → reaches the route, returns
    `INVALID_CREDENTIALS` (recovery flow not blocked).
19. WebSocket: connect with valid ticket → upgraded; with expired
    ticket → 4001 close.

### Frontend regression

20. From `frontend/`: `bun run test` → all green.
21. From `frontend/`: `bun run test:e2e` → all green. Any failure here
    is treated as backend HTTP-contract regression to fix in backend.

## Suggested execution order

Each step is one atomic commit. Tests must be green at each step.

1. **T-19-01 baseline snapshot**: pin pytest inventory + commit
   `.planning/DEVIATIONS.md` with Phase 13 waiver entry.
2. **T-19-02 services module**: create `app/core/services.py` with
   module-level singletons (`password_service`, `csrf_service`,
   `token_service`, `ws_ticket_service`, ML services). Wire one route
   off it as smoke test. Existing container coexists.
3. **T-19-03 get_db + repo deps**: implement `get_db` and
   `get_*_repo` chain in `app/api/dependencies.py`. New helpers
   coexist with old `_container.X()` calls.
4. **T-19-04 authenticated_user**: implement `authenticated_user`
   + `_resolve_bearer` + `_resolve_cookie` in
   `app/api/dependencies.py`. Sliding cookie refresh inside
   `_resolve_cookie`.
5. **T-19-05 csrf_protected dep**: convert CSRF check to a `Depends`
   factory; apply to routers as `dependencies=[...]`. Keep
   `CsrfMiddleware` registered alongside (belt + suspenders during
   migration).
6. **T-19-06 first route migration**: rewrite `/api/account/me` to use
   `Depends(authenticated_user)`. Verify account tests green. If green,
   continue; if red, iterate the dep until green BEFORE proceeding.
7. **T-19-07..N route sweep**: migrate each remaining router one
   commit at a time (`auth_routes`, `key_routes`, `billing_routes`,
   `task_api`, `account_routes` continued). Tests green per commit.
8. **T-19-08 WebSocket migration**: rewrite `websocket_api.py` +
   `ws_ticket_routes.py` with explicit `SessionLocal()` blocks +
   module-level singletons.
9. **T-19-09 background task migration**: rewrite
   `whisperx_wrapper_service.py` with `with SessionLocal() as db:`
   blocks; verify W1 finally still releases slot on failure.
10. **T-19-10 delete DualAuthMiddleware + AUTH_V2 branches**: remove
    `DualAuthMiddleware` registration, `BearerAuthMiddleware` import +
    registration, `is_auth_v2_enabled()` calls, prod guard. Single
    middleware stack.
11. **T-19-11 delete CsrfMiddleware class**: now that all routers use
    `Depends(csrf_protected)`, remove the middleware. Update tests
    that asserted middleware presence.
12. **T-19-12 delete container.py**: remove `app/core/container.py`,
    remove `Container()` instantiation in `main.py`, remove
    `set_container(container)` call. Run grep gates 1-4. All ZERO.
13. **T-19-13 add no-leak regression test**:
    `tests/integration/test_no_session_leak.py`. CI gate.
14. **T-19-14 frontend test pass**: `bun run test` + `bun run test:e2e`.
    Fix any backend regressions surfaced.
15. **T-19-15 dead code sweep**: remove inline `session.close()`
    finallys, `PUBLIC_ALLOWLIST`, `_is_public`,
    `_set_state_anonymous`, `set_container` helper.
16. **T-19-16 final verification**: run all 21 verification gates;
    write `19-VERIFICATION.md`.

## Branch + PR

- Branch: `gsd/phase-19-auth-di-refactor`.
- Single PR. Each T-19-NN is one commit. Each commit must leave the
  test suite green so any commit is independently revertable.
- Rollback procedure: if mid-refactor a deal-breaker surfaces (e.g. a
  hidden caller of `_container` discovered late), abort with `git reset
  --hard origin/main` on the branch — no partial-state commits land on
  main.

## Resolved questions (decisions baked into the implementation)

Originally listed as gray areas for the planner; resolved during execution
and reconfirmed at v1.2 milestone close:

- ~~Q1. Should `get_db` be sync or async?~~ → **sync**. SQLAlchemy 2.x
  sync `Session` matches the rest of the codebase; no perf reason to
  switch yet (revisit Phase 20+ if needed).
- ~~Q2. Should `authenticated_user` accept `Optional[User]`?~~ → **two
  separate deps**. `authenticated_user` (required) + future
  `authenticated_user_optional` (when needed). More idiomatic FastAPI.
- ~~Q3. Module globals vs `@lru_cache(maxsize=1)` factories?~~ →
  **`@lru_cache(maxsize=1)`**. Lazy-init is explicit; matches the
  ffmpeg probe pattern added during v1.2 close (`app/audio.py`).
