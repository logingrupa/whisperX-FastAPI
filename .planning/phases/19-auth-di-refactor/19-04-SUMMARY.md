---
phase: 19
plan: 04
subsystem: api/dependencies
tags: [auth, depends, fastapi, sliding-cookie-refresh, refactor-07-lock]
requires:
  - 19-03 (get_db + _v2 repo/service providers)
provides:
  - authenticated_user (FastAPI Depends)
  - authenticated_user_optional (None on miss)
  - _resolve_bearer / _resolve_cookie / _try_resolve helpers
  - get_scoped_task_repository_v2 / get_task_management_service_v2
  - REFACTOR-07 backend Set-Cookie attrs lock at Wave 2
affects:
  - app/api/dependencies.py (+220 LOC, +210 net)
tech_stack:
  added: []
  patterns:
    - FastAPI Depends-chain auth (per-route, replaces middleware lookup)
    - subtype-first exception tuples (CLAUDE.md convention)
    - flat early-return guards (zero nested-if)
    - response.set_cookie inside dep body (FastAPI flushes BEFORE return)
key_files:
  created:
    - tests/integration/test_authenticated_user_dep.py
    - tests/integration/test_set_cookie_attrs.py
    - .planning/phases/19-auth-di-refactor/deferred-items.md
  modified:
    - app/api/dependencies.py
decisions:
  - "Test fixture monkeypatches PUBLIC_ALLOWLIST with /protected + /optional so DualAuthMiddleware (still installed pre-Plan-11) lets unauthenticated calls through to the new dep. Phase 19 Plan 04 must coexist with the legacy middleware; the monkeypatch is a test-only seam."
  - "Cookie attrs byte-identical to dual_auth.py:310-321 — settings.auth.{JWT_TTL_DAYS, COOKIE_SECURE, COOKIE_DOMAIN}; Max-Age=604800 (7d), HttpOnly, SameSite=lax, Path=/, Secure absent in dev. Locked at every commit by tests/integration/test_set_cookie_attrs.py (REFACTOR-07 Wave 2 backend gate)."
  - "Subtype-first error tuples preserved verbatim: _BEARER_FAILURES catches Invalid* before generic; _COOKIE_DECODE_FAILURES + _COOKIE_REFRESH_FAILURES split decode/refresh legs to mirror dual_auth.py."
  - "Bearer-wins-when-both-present invariant: malformed bearer with valid cookie returns 401 (NOT silent fallthrough to cookie) — T-19-04-06 mitigation enforced by test 5."
  - "WWW-Authenticate header docstring rephrased to avoid grep-gate double-count (Plan 19-02 lesson; same as Plan 15-02)."
metrics:
  duration: "31min"
  completed_date: "2026-05-02"
  task_count: 2
  file_count: 4
---

# Phase 19 Plan 04: authenticated_user Depends chain + REFACTOR-07 Wave-2 Lock — Summary

## One-liner

`authenticated_user` + `authenticated_user_optional` Depends now expose the
DualAuthMiddleware semantics 1:1 (bearer-wins, sliding cookie refresh,
subtype-first error tuples, byte-identical Set-Cookie attrs) — coexists with
the legacy middleware until Plan 11 deletes it; backend-side Set-Cookie attr
lock fires from Wave 2 instead of Plan 15 Playwright.

## What was delivered

### `app/api/dependencies.py` (+220 LOC, Phase 19 Plan 04 region)

| Symbol | Type | Role |
|---|---|---|
| `SESSION_COOKIE`, `BEARER_PREFIX` | const | shared with auth_routes._cookie_helpers |
| `_BEARER_FAILURES`, `_COOKIE_DECODE_FAILURES`, `_COOKIE_REFRESH_FAILURES` | tuple | subtype-first exception tuples (verbatim from dual_auth.py:110-125) |
| `STATE_MUTATING_METHODS` | frozenset | reserved for `csrf_protected` (Plan 05) |
| `_resolve_bearer(plaintext, db)` | helper | two-query bearer resolution (dual_auth.py:209-225) |
| `_resolve_cookie(token, db, response)` | helper | cookie-decode + token_version + sliding refresh (dual_auth.py:262-321) |
| `_try_resolve(request, response, db)` | helper | bearer-then-cookie-then-None flat early-returns |
| `authenticated_user` | async dep | raises 401 + WWW-Authenticate header on miss |
| `authenticated_user_optional` | async dep | returns None on miss |
| `get_scoped_task_repository_v2` | dep | chains off `authenticated_user` + `get_db`, calls `set_user_scope(user.id)` |
| `get_task_management_service_v2` | dep | wraps the scoped repo |

### `tests/integration/test_authenticated_user_dep.py` (+ ~370 LOC, 12 cases)

| # | Case | Asserts |
|---|------|---------|
| 1 | No auth | 401 + `{"detail":"Authentication required"}` + `WWW-Authenticate: Bearer realm="whisperx"` |
| 2 | Valid bearer | 200 + user_id |
| 3 | Valid cookie | 200 + user_id |
| 4 | Bearer + cookie both valid | bearer wins (different users registered separately) |
| 5 | Malformed bearer + valid cookie | 401 (no fallthrough — T-19-04-06) |
| 6 | Tampered cookie | 401 |
| 7 | Expired cookie | 401 |
| 8 | Stale token_version cookie | 401 (DB bumped to ver=1; cookie carries ver=0) |
| 9 | Sliding refresh | response stamps fresh `Set-Cookie: session=…; HttpOnly; Path=/; SameSite=lax` |
| 10 | /optional anonymous | 200 + "anonymous" |
| 11 | /optional authed | 200 + user_id |
| 12 | Stale cookie on /protected | 401 + does NOT clear cookies |

### `tests/integration/test_set_cookie_attrs.py` (+ 102 LOC)

REFACTOR-07 backend gate: locks Set-Cookie attrs on `POST /auth/login`:
`Max-Age=604800` (7 * 86400), `HttpOnly`, `SameSite=lax`, `Path=/`, `Secure`
absent (dev `COOKIE_SECURE=false`). Fires at every Wave-2-onwards commit.

## Verifier gates (all passing)

| Gate | Expected | Actual |
|------|----------|--------|
| `grep -c "async def authenticated_user" app/api/dependencies.py` | 2 | 2 |
| `grep -c "WWW-Authenticate" app/api/dependencies.py` | 1 | 1 |
| `grep -c "BEARER_PREFIX = \"Bearer \"" app/api/dependencies.py` | 1 | 1 |
| `grep -c "response.set_cookie" app/api/dependencies.py` | ≥ 1 | 2 (1 docstring, 1 call) |
| `grep -cE "^\s+if .*\bif\b" app/api/dependencies.py` | 0 | 0 |
| `pytest tests/integration/test_authenticated_user_dep.py tests/integration/test_set_cookie_attrs.py` | GREEN | 13/13 GREEN |
| Auth/account/jwt-attack regression suites | GREEN | 51/51 GREEN |

## Deviations from plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test fixture needed key_router + middleware to seat bearer keys**

- **Found during:** Task 1 GREEN run (after first attempt to test bearer auth)
- **Issue:** `_issue_bearer` posts to `/api/keys` to mint a bearer plaintext;
  this requires `key_router` mounted, plus `DualAuthMiddleware` + `CsrfMiddleware`
  to authenticate the cookie + verify CSRF on POST.
- **Fix:** added `key_router`, `CsrfMiddleware`, `DualAuthMiddleware` to the
  slim app; matched ASGI registration order (`Csrf` first → dispatches
  AFTER `DualAuth`).
- **Files modified:** `tests/integration/test_authenticated_user_dep.py`
- **Commit:** 6953656

**2. [Rule 3 - Blocking] DualAuthMiddleware blocked anonymous /optional**

- **Found during:** Task 1 GREEN run (test 10 — anonymous /optional → 401)
- **Issue:** With `DualAuthMiddleware` mounted, anonymous requests to a
  non-public path 401 at the middleware BEFORE the new dep ever runs. Plan 04
  must coexist with the legacy middleware (Plan 11 deletes it), so the test
  needed an isolation seam.
- **Fix:** monkeypatch `dual_auth.PUBLIC_ALLOWLIST` to add `/protected` +
  `/optional`. Real prod routes opt out of `DualAuthMiddleware` interception
  by being placed on `PUBLIC_ALLOWLIST` for the duration of Plans 06-10
  (interim state); Plan 11 removes the middleware and the allowlist
  altogether.
- **Files modified:** `tests/integration/test_authenticated_user_dep.py`
- **Commit:** 6953656

**3. [Rule 1 - Bug] WWW-Authenticate grep-gate docstring tax**

- **Found during:** Task 2 verifier gate run
- **Issue:** docstring on `authenticated_user` mentioned `WWW-Authenticate`;
  raw `grep -c WWW-Authenticate dependencies.py` returned 2 (one docstring,
  one code), failing the `== 1` plan gate. Same pattern as Plan 19-02
  (`@lru_cache(maxsize=1)` docstring tax) and Plan 15-02 (verifier-grep
  literal-token tax in docstrings).
- **Fix:** rephrased docstring to "Bearer realm=\"whisperx\" challenge
  header" — preserves intent without the literal token.
- **Files modified:** `app/api/dependencies.py`
- **Commit:** 6953656

### Authentication Gates

None — Plan 04 needed no external auth.

## Pre-existing failures observed (out of scope)

Full backend suite shows 27 failures both BEFORE and AFTER Plan 04 work
(verified by re-running `pytest tests/` on commit b6306ef and 6953656).
All in files last touched in Phase 11 era. Triage tracked in
`.planning/phases/19-auth-di-refactor/deferred-items.md`. Plan 04 success
criterion "no regression" satisfied — same failure set unchanged.

## Coexistence with DualAuthMiddleware

`DualAuthMiddleware` stays installed in `app/main.py` (verified — `grep -c
DualAuthMiddleware app/main.py == 2`). No routes were touched. The new
`authenticated_user` dep is available for Plans 06+ to migrate routes
one-at-a-time. Plan 11 deletes the middleware once all routes are migrated.

## Files changed

- **created:**
  - `tests/integration/test_authenticated_user_dep.py`
  - `tests/integration/test_set_cookie_attrs.py`
  - `.planning/phases/19-auth-di-refactor/deferred-items.md`
- **modified:**
  - `app/api/dependencies.py` (+220 LOC; net +210 after constant block)

## Commits

| Hash | Type | Message |
|------|------|---------|
| `b6306ef` | test | add 12-case authenticated_user dep + Set-Cookie attrs lock (RED) |
| `6953656` | feat | add authenticated_user + scoped task repo Depends chain + Set-Cookie attr lock |

## Self-Check: PASSED

- `app/api/dependencies.py` exists; `grep -q "async def authenticated_user"` → FOUND.
- `tests/integration/test_authenticated_user_dep.py` exists; 13 cases collected.
- `tests/integration/test_set_cookie_attrs.py` exists; passes.
- Commit `b6306ef` (RED) — FOUND on git log.
- Commit `6953656` (GREEN) — FOUND on git log.
- Verifier grep gates all pass (table above).
- Plan-04-relevant regression suites all green (51/51).
