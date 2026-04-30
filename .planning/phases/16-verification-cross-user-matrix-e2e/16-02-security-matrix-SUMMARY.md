---
phase: 16-verification-cross-user-matrix-e2e
plan: 02
subsystem: testing
tags: [verification, cross-user, anti-enumeration, parametrize, security-matrix]

# Dependency graph
requires:
  - phase: 16-verification-cross-user-matrix-e2e
    provides: tests/integration/_phase16_helpers.py — ENDPOINT_CATALOG, _seed_two_users, _insert_task, _register
  - phase: 13-auth-and-rate-limit-services
    provides: DualAuthMiddleware + CsrfMiddleware (ASGI middleware stack)
  - phase: 13-auth-and-rate-limit-services
    provides: 8 task-touching endpoints (auth/task/key/account/ws_ticket routers)
  - phase: 11-auth-core-modules-services-di
    provides: Container DI + InvalidCredentialsError/ValidationError handlers
provides:
  - VERIFY-01 cross-user matrix — 17 parametrized tests proving User A's resources invisible to User B
  - Locked invariant: foreign-id 404 body bytewise-identical to unknown-id 404 body (anti-enumeration)
  - Pattern: ASGI middleware order (CSRF registered first -> DualAuth runs first on dispatch) verified end-to-end
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DRY parametrization: @pytest.mark.parametrize over module-level ENDPOINT_CATALOG (single source for foreign + self legs)"
    - "Two-TestClient pattern with cookies.clear-free isolation (separate jars per user)"
    - "Flat dict lookup for self-leg expected status (_SELF_STATUS), no nested-if"
    - "Tiger-style failure messages embedding response.text on every assertion"
    - "Helper composition: _request + _format_url + _ws_ticket_body + _seed_resources (each SRP)"

key-files:
  created:
    - tests/integration/test_security_matrix.py
  modified: []

key-decisions:
  - "ASGI middleware registration order locked: CsrfMiddleware first, DualAuthMiddleware second — registration is REVERSED on dispatch so DualAuth runs FIRST (Pitfall 3, comment block in fixture documents the rationale)"
  - "_SELF_STATUS hardcoded as flat dict (method, path_tmpl) -> int rather than nested if-else; assertion `len(_SELF_STATUS) == len(ENDPOINT_CATALOG)` enforces no drift"
  - "POST /api/keys returns id as int (CreateKeyResponse.id field); helpers stringify via str(key_id) so `{key_id}` placeholder substitutes cleanly into URL templates"
  - "Foreign-leg expected status driven entirely from ENDPOINT_CATALOG[2] — no test-local override; if catalog says 200/204 (caller-scoped) the test asserts 200/204, not 404"
  - "_ws_ticket_body extracted as named helper (not inline ternary) so the catalog-template -> body mapping has a single SRP-clean home; future endpoints needing bodies extend this helper, not the test bodies"

requirements-completed: [VERIFY-01]

# Metrics
duration: 5 min
completed: 2026-04-30
---

# Phase 16 Plan 02: Cross-User Security Matrix Summary

**17 parametrized integration tests (8 foreign-leg cases, 8 self-leg positive controls, 1 anti-enumeration body-parity assertion) prove that User A's tasks/keys/usage are invisible to User B across every task-touching endpoint — the milestone-gate invariant for VERIFY-01.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-30T12:44:15Z
- **Completed:** 2026-04-30T12:49:41Z
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments

- 17 tests pass first-try; zero deviations needed; zero implementation bugs surfaced
- Cross-user matrix covers all 8 task-touching endpoints from ENDPOINT_CATALOG (GET /task/all, GET /task/{id}, DELETE /task/{id}/delete, GET /tasks/{id}/progress, POST /api/ws/ticket, DELETE /api/keys/{key_id}, DELETE /api/account/data, GET /api/account/me)
- Foreign-leg expected status semantics encoded once in ENDPOINT_CATALOG: 404 for resource-scoped (anti-enumeration), 200 for caller-scoped collection (returns B's empty list, not A's), 204 for caller-scoped write against B's empty namespace
- Self-leg positive controls assert exact route status codes (200/201/204) via flat dict lookup — proves foreign-leg failures are NOT route-broken
- Anti-enumeration parity: foreign-id 404 body bytewise-identical to unknown-id 404 body verified via shared `_task_not_found_handler` JSON response
- ASGI middleware order locked: CsrfMiddleware registered FIRST so DualAuth runs FIRST on dispatch (Pitfall 3 mitigated end-to-end)
- limiter.reset() called in BOTH fixture setup AND teardown (Pitfall 1 — rate-limit poisoning between tests)
- Two TestClient instances per test, separate cookie jars (Pitfall 2 — jar collision masks isolation bugs)

## Task Commits

1. **Task 1: full_app fixture + DRY helpers** — `248bf05` (test)
2. **Task 2: parametrized matrix + anti-enum parity** — `16379e2` (test)

## Files Created/Modified

- `tests/integration/test_security_matrix.py` — 339 lines; module docstring + imports + `_task_not_found_handler` + 3 fixtures (tmp_db_url, session_factory, full_app) + 4 helpers (_create_key, _seed_resources, _request, _format_url, _ws_ticket_body) + `_SELF_STATUS` dict + 3 test functions (test_foreign_user_blocked parametrized 8 cases, test_self_user_succeeds parametrized 8 cases, test_anti_enum_body_parity_unknown_vs_foreign_task)

## Decisions Made

- **ASGI middleware registration order:** Registered CsrfMiddleware FIRST and DualAuthMiddleware SECOND. ASGI reverses registration on dispatch — DualAuth therefore runs first and populates request.state.auth_method before CsrfMiddleware reads it. Fixture comment block documents the rationale (Pitfall 3 from RESEARCH.md).
- **_SELF_STATUS as flat dict:** Lookup `(method, path_tmpl) -> int` instead of nested if-elif chains. Drift-check assertion `len(_SELF_STATUS) == len(ENDPOINT_CATALOG)` fails loud if catalog grows without the table being updated.
- **String-coercion of key_id:** POST /api/keys returns int `id`. The `{key_id}` URL placeholder requires str. `_seed_resources` does `str(key_id)` once so resources dict uniformly typed (str values), URL templating stays a single `template.format(**resources)` call (DRT).
- **_ws_ticket_body as named helper:** Extracted instead of inline ternary inside each test. Future endpoints needing bodies extend this single helper rather than each test body — keeps tests pure assertion-of-contract, helpers own request shaping (SRP).
- **DELETE /task/{id}/delete self-leg = 200 (not 204):** Verified against task_api.py:83 — no status_code= attribute on the decorator + handler returns a response model, so default 200 applies. This contradicts the plan's hint that "DELETE -> 204"; the locked _SELF_STATUS table is correct per actual route source.

## Deviations from Plan

None — plan executed exactly as written.

The plan's <action> body for Task 2 explicitly noted "Verify exact status codes against the four route files before locking the table" and the locked self-status table in the plan body matched the route source verbatim. No corrections needed.

## Issues Encountered

None. All 17 tests passed first run. No retries, no Rule 1/2/3 deviations.

The pre-existing `tests/integration/test_migration_smoke.py` untracked file in the working tree is from a parallel agent (Plan 16-06) — not in scope for this plan and left untouched.

## User Setup Required

None — no external service configuration.

## Next Phase Readiness

VERIFY-01 closed. Plan 16-02 done. Wave 1 parallel-safe — does not touch any other plan's files. Ready for Plan 16-03 (JWT attacks), 16-04 (CSRF enforcement), 16-05 (WS ticket safety), 16-06 (migration smoke) — all wave-1 siblings consume `_phase16_helpers.py` independently.

**Verification commands future plans / verifier can rerun:**
- `.venv/Scripts/python.exe -m pytest tests/integration/test_security_matrix.py -v` — expects 17 passed
- `grep -nE "add_middleware\(CsrfMiddleware|add_middleware\(DualAuthMiddleware" tests/integration/test_security_matrix.py` — Csrf line < DualAuth line
- `grep -c "limiter.reset()" tests/integration/test_security_matrix.py` — returns 3 (>= 2)
- `grep -nE "^\s+if .*\bif\b" tests/integration/test_security_matrix.py | wc -l` — returns 0 (nested-if invariant)

---
*Phase: 16-verification-cross-user-matrix-e2e*
*Completed: 2026-04-30*

## Self-Check: PASSED

- File exists: `tests/integration/test_security_matrix.py` (339 lines, FOUND)
- Commit `248bf05`: FOUND in `git log --oneline --all`
- Commit `16379e2`: FOUND in `git log --oneline --all`
- Plan-level verification: 17 tests pass; nested-if grep == 0; CSRF line before DualAuth line; limiter.reset() count == 3; ENDPOINT_CATALOG single-source (8 entries imported, not redefined)
- Task 1 acceptance: 5/5 criteria pass (Csrf == 1, DualAuth == 1, CSRF before DualAuth, limiter.reset >= 2, helper-import == 1)
- Task 2 acceptance: 4/4 criteria pass (>= 17 tests collected, exit code 0, nested-if invariant 0, parity test exists)
- Plan success criteria: 8 foreign + 8 self + 1 body-parity = 17 passing tests; ENDPOINT_CATALOG imported (DRT); ASGI order locked; limiter.reset() in setup AND teardown; two TestClients per test
