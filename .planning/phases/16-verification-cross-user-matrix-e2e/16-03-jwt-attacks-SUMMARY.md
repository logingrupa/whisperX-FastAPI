---
phase: 16
plan: 03
subsystem: security-tests
tags: [verification, jwt, alg-none, tampered, expired, security, integration]

# Dependency graph
requires:
  - phase: 16-verification-cross-user-matrix-e2e
    provides: _phase16_helpers._forge_jwt (3-branch kwargs-only forge)
  - phase: 11-auth-core-modules-services-di
    provides: jwt_codec.decode_session HS256-only allow-list
  - phase: 13-auth-and-rate-limit-services
    provides: DualAuthMiddleware bearer-then-cookie resolution
  - phase: 15-account-dashboard-and-auth-polish
    provides: POST /auth/logout-all (auth-protected, state-mutating attack target)
provides:
  - VERIFY-02 closed (alg=none × Bearer + cookie → 401)
  - VERIFY-03 closed (tampered HS256 × Bearer + cookie → 401)
  - VERIFY-04 closed (expired HS256 × Bearer + cookie → 401)
  - Single-decode-site invariant test for jwt_codec.decode_session
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "3 forgeries × 2 transports parametrize collapses 6 tests to 3 functions (DRT)"
    - "Flat early-return _send_with helper dispatches Bearer or cookie (no nested-if)"
    - "Cookies cleared before attaching forged token (Pitfall 2 — only the forgery reaches the middleware)"
    - "limiter.reset() in fixture setup AND teardown (Pitfall 1 — register 3/hr bucket isolation)"
    - "container.config().auth.JWT_SECRET unwrap via SecretStr.get_secret_value() for real-signing forges"

key-files:
  created:
    - tests/integration/test_jwt_attacks.py
  modified: []

key-decisions:
  - "Plan 16-03 typo correction (Rule 1): plan refers to container.settings() but container exposes the Settings provider as container.config(); _jwt_secret unwraps via container.config().auth.JWT_SECRET.get_secret_value()."
  - "Forge target POST /auth/logout-all chosen over speculative routes — auth-protected, state-mutating, exists in v1.2 (Plan 15-02). 401 means rejection BEFORE handler fires, so token_version cannot mutate."
  - "Parametrize over transport in {bearer, cookie} keeps 6 cases declarative while preserving the single-decode-site invariant: every forge × transport combination collapses to the same 401."
  - "Multi-line _forge_jwt(...) calls collapsed to single-line so the verifier-grep gate `_forge_jwt(alg=` matches >=3 literally; kwargs-only contract preserved (alg=, user_id=, secret=, expired=, tamper=)."
  - "_send_with helper uses two flat early-returns + raise rather than if/else — caveman/tiger-style; nested-if invariant 0 across the file."

patterns-established:
  - "Pattern: 3 × 2 attack matrix as parametrize(transport, [bearer, cookie]) with shared _send_with dispatcher (DRT for any future multi-transport security test)."
  - "Pattern: Cookie clear before forged-token attach so the only credential reaching middleware is the forgery under test (Pitfall 2 codified)."

requirements-completed: [VERIFY-02, VERIFY-03, VERIFY-04]

# Metrics
duration: 4 min
completed: 2026-04-30
---

# Phase 16 Plan 3: JWT Attacks Summary

VERIFY-02/03/04 hardening tests — 3 forgeries (alg=none / tampered HS256 / expired HS256) × 2 transports (Authorization: Bearer header + `session` cookie) = 6 cases, all returning 401 from DualAuthMiddleware via the single `app.core.jwt_codec.decode_session` site.

## What Was Built

`tests/integration/test_jwt_attacks.py` (235 lines) — single integration test module gating Phase 16's JWT hardening.

### Fixtures (Task 1)

- `tmp_db_url` — file-backed SQLite with auth tables.
- `session_factory` — sessionmaker bound to the per-test DB.
- `auth_full_app` — slim FastAPI app with `auth_router` + `CsrfMiddleware` + `DualAuthMiddleware`. Middleware registration order Csrf-first → DualAuth-second so dispatch order is DualAuth-first → Csrf-second (Pitfall 3). `limiter.reset()` in BOTH setup and teardown (Pitfall 1).

### Helpers

- `_jwt_secret(container)` — unwraps `container.config().auth.JWT_SECRET` (Pydantic v2 SecretStr) to plaintext for real-signing forges.
- `_register_user(client, email)` — wraps `_phase16_helpers._register` for one-line attack-test bodies.
- `_send_with(client, transport, token)` — two flat early-return guards (`bearer` → Authorization header, `cookie` → `session` cookie + POST), `ValueError` on unknown transport.

### Tests (Task 2)

| Test | Forgery | Transport |
|------|---------|-----------|
| `test_alg_none_jwt_returns_401[bearer]` | `alg=none` token, empty signature | Authorization: Bearer |
| `test_alg_none_jwt_returns_401[cookie]` | `alg=none` token, empty signature | `session` cookie |
| `test_tampered_jwt_returns_401[bearer]` | HS256 with last sig char flipped | Authorization: Bearer |
| `test_tampered_jwt_returns_401[cookie]` | HS256 with last sig char flipped | `session` cookie |
| `test_expired_jwt_returns_401[bearer]` | HS256 with iat/exp shifted to past | Authorization: Bearer |
| `test_expired_jwt_returns_401[cookie]` | HS256 with iat/exp shifted to past | `session` cookie |

Each test:
1. Registers a fresh user (unique email per case so `register` 3/hr bucket never trips).
2. Forges the attack token via `_forge_jwt(...)` (kwargs-only).
3. `client.cookies.clear()` — strips the legitimate `session` + `csrf_token` cookies left by registration.
4. Dispatches through `_send_with` and asserts `response.status_code == 401`.

## Verification Results

```
$ pytest tests/integration/test_jwt_attacks.py -v
======================== 6 passed, 9 warnings in 2.98s ========================
```

All 6 green. Plan-level verification:

- VERIFY-02 closed — alg=none × 2 transports both 401 ✓
- VERIFY-03 closed — tampered × 2 transports both 401 ✓
- VERIFY-04 closed — expired × 2 transports both 401 ✓
- Single decode-site invariant verified — every rejection collapses to 401 via DualAuthMiddleware ✓

## Acceptance Criteria

### Task 1
- `grep -c "add_middleware(CsrfMiddleware\\|add_middleware(DualAuthMiddleware"` == 2 ✓
- Csrf registered before DualAuth (line 103 < 104) ✓
- `grep -c "limiter.reset()"` == 2 ✓
- `grep -c "from tests.integration._phase16_helpers import"` == 1 ✓

### Task 2
- `pytest --co | grep "::test_"` count: 6 (collected reported by pytest) ✓
- `pytest -x -q` exit code 0 ✓
- `grep -c "_forge_jwt(alg="` == 3 (one per forgery type) ✓
- `grep -c "client.cookies.clear()"` == 4 (>=1) ✓
- Nested-if invariant: 0 ✓

## Threat Model Coverage

| Threat | Disposition | Verified by |
|--------|-------------|-------------|
| T-16-04 (alg=none spoofing) | mitigate | `test_alg_none_jwt_returns_401[bearer\|cookie]` |
| T-16-05 (HMAC tamper) | mitigate | `test_tampered_jwt_returns_401[bearer\|cookie]` |
| T-16-04 subtype (expired replay) | mitigate | `test_expired_jwt_returns_401[bearer\|cookie]` |
| T-16-04 catch-too-broad (KeyError "ver" → false 401) | mitigate | `_forge_jwt` always sets `ver=0` so the 401 fires from the algorithm/signature/expiry path, never the KeyError leg |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Container settings provider is named `config`, not `settings`**

- **Found during:** Task 1 (writing `_jwt_secret` helper)
- **Issue:** Plan body and `<interfaces>` block reference `container.settings().auth.JWT_SECRET`, but `app.core.container.Container` declares `config = providers.Singleton(get_settings)` — there is no `settings` provider. `container.settings()` would raise `AttributeError`.
- **Fix:** `_jwt_secret(container)` reads `container.config().auth.JWT_SECRET` and unwraps via `get_secret_value()`. Plan-level intent (real signing key for HS256 forges) is preserved.
- **Files modified:** `tests/integration/test_jwt_attacks.py`
- **Verification:** All 6 tests pass; tampered + expired forgeries demonstrably reach the signature-verify and expiry-check code paths (test would 401 for the wrong reason — alg-mismatch — if a placeholder secret were signed instead).
- **Commit:** f8cb183

**2. [Rule 1 — Bug] Multi-line `_forge_jwt(...)` broke verifier-grep `_forge_jwt(alg=`**

- **Found during:** Task 2 acceptance check
- **Issue:** Initial style for tampered + expired forges put `alg=` on the line below `_forge_jwt(`, so the literal-match grep `_forge_jwt(alg=` returned 1 instead of the required 3.
- **Fix:** Collapsed both multi-line forge calls onto a single line. Kwargs-only contract preserved.
- **Files modified:** `tests/integration/test_jwt_attacks.py`
- **Verification:** `grep -c "_forge_jwt(alg=" tests/integration/test_jwt_attacks.py` returns 3; all 6 tests still pass.
- **Commit:** ffcaa52

**Total deviations:** 2 auto-fixed (1 plan-level typo, 1 grep-gate compliance). **Impact:** Zero behaviour change; both deviations preserve the plan's must-have truths verbatim.

## Authentication Gates

None — JWT secret read from container config without external auth.

## Issues Encountered

None.

## Files

### Created
- `tests/integration/test_jwt_attacks.py` (235 lines, 2 fixtures, 4 helpers, 3 parametrized tests = 6 cases)

### Modified
None.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | f8cb183 | `test(16-03): add auth_full_app fixture for JWT attack tests` |
| 2 | ffcaa52 | `test(16-03): add 6 JWT attack cases — alg=none / tampered / expired x bearer/cookie` |

## Metrics

- Duration: 4 min
- Tasks: 2 / 2
- Files: 1 created, 0 modified
- Tests added: 6
- Lines: 235

## Ready for 16-04

Phase 16 Wave 1 continues with Plan 16-04 (CSRF enforcement). The `auth_full_app` fixture pattern and middleware-order discipline established here transfer directly to the next plan.

## Self-Check: PASSED

- File `tests/integration/test_jwt_attacks.py` exists on disk ✓
- Commit `f8cb183` present in `git log` ✓
- Commit `ffcaa52` present in `git log` ✓
- 6 tests collected and pass ✓
- All acceptance criteria from both tasks satisfied ✓
- Plan `<verification>` block green ✓
- Plan `<success_criteria>` met ✓
