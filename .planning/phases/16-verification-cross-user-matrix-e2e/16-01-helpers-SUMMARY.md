---
phase: 16-verification-cross-user-matrix-e2e
plan: 01
subsystem: testing
tags: [verification, test-helpers, dry, jwt, csrf, alembic, ws]

# Dependency graph
requires:
  - phase: 13-auth-and-rate-limit-services
    provides: auth_router /auth/register cookie pair (session + csrf_token)
  - phase: 13-auth-and-rate-limit-services
    provides: ws_ticket_routes WS_POLICY_VIOLATION semantics (1008)
  - phase: 11-auth-core-modules-services-di
    provides: jwt_codec HS256-only decode policy
  - phase: 10-database-foundation-alembic
    provides: alembic subprocess invocation pattern (test_alembic_migration.py)
provides:
  - Single DRT helper module for Phase 16's five test files
  - ENDPOINT_CATALOG (8 entries) — VERIFY-01 cross-user matrix surface
  - JWT forge with three deterministic branches (alg=none / HS256 expired / HS256 tamper)
  - CSRF cookie capture from /auth/register response jar
  - venv-portable alembic subprocess wrapper
  - WS_POLICY_VIOLATION constant (1008) as single source
affects: [16-02-security-matrix, 16-03-jwt-attacks, 16-04-csrf-enforcement, 16-05-ws-ticket-safety, 16-06-migration-smoke]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy ORM import inside helper to keep module loadable without DB engine
    - Flat early-return guards (no nested-if) for multi-branch helpers
    - Tiger-style boundary asserts on every external response/cookie read
    - kwargs-only signatures on multi-arg helpers (_forge_jwt, _insert_task)
    - Module-level constant ENDPOINT_CATALOG hardcoded (no env-driven branching)

key-files:
  created:
    - tests/integration/_phase16_helpers.py
  modified: []

key-decisions:
  - "Endpoint catalog hardcoded as module-level constant (not env-driven) — DRY single source for VERIFY-01 matrix and VERIFY-06 CSRF surface"
  - "JWT forge bypasses PyJWT for alg=none (PyJWT 2.x refuses alg=none on encode); HS256 paths use real jwt.encode then post-process for tamper"
  - "Lazy import of ORMTask inside _insert_task keeps module loadable without DB engine bound (allows isolated import tests)"
  - "_seed_two_users takes two TestClients (not app+session_factory) per plan interfaces — caller controls jar isolation"
  - "_run_alembic mirrors test_alembic_migration.py:34-53 verbatim — single venv-portable pattern across both phases"

patterns-established:
  - "Pattern: Phase-scoped shared helper module (tests/integration/_phase{N}_helpers.py) for DRT across multiple test files"
  - "Pattern: Three-branch _forge_jwt with kwargs-only signature and flat early-returns (alg-none / HS256-expired / HS256-tamper)"
  - "Pattern: Endpoint catalog as list[tuple[method, path_template, expected_foreign_status, requires_csrf]] — single-source matrix"
  - "Pattern: Tiger-style cookie assertion in _issue_csrf_pair — fails loud on missing session/csrf cookies"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-04-30
---

# Phase 16 Plan 01: Wave 0 DRT Shared Helpers Summary

**Single 269-line DRT helper module exporting 7 helpers + ENDPOINT_CATALOG (8 entries) + WS_POLICY_VIOLATION constant — consumed unchanged by plans 16-02..06 to keep verification tests file-disjoint and parallel-safe.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-30T12:36:38Z
- **Completed:** 2026-04-30T12:39:50Z
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments

- ENDPOINT_CATALOG with 8 task-touching endpoints, expected_foreign_status grounded in actual @router decorators (anti-enum 404, scoped 200, soft-204) — verified via grep app/api/
- Three-branch JWT forge (alg=none / HS256 expired / HS256 tamper) using flat early-returns, kwargs-only signature, deterministic claim shape matching app/core/jwt_codec.py contract
- _issue_csrf_pair captures both session + csrf_token cookies from /auth/register jar with tiger-style asserts on missing-cookie regressions
- _run_alembic subprocess wrapper venv-portable (sys.executable + DB_URL env override) per Plan 10-04 lesson
- _insert_task lazy-imports ORMTask so module loads cleanly without bound DB engine (validated: `from tests.integration import _phase16_helpers` succeeds standalone)

## Task Commits

Each task committed atomically:

1. **Task 1: constants + endpoint catalog + seeding helpers** — `efaeb08` (test)
2. **Task 2: JWT forge + CSRF capture + alembic subprocess helpers** — `e1a09ea` (test)

## Files Created/Modified

- `tests/integration/_phase16_helpers.py` — 269 lines; constants (WS_POLICY_VIOLATION, JWT_HS256, JWT_ALG_NONE, REPO_ROOT), ENDPOINT_CATALOG (8 entries), 7 helpers (_register, _seed_two_users, _insert_task, _b64url, _forge_jwt, _issue_csrf_pair, _run_alembic)

## Decisions Made

- **ENDPOINT_CATALOG status semantics:** 200 = caller scoped to own (empty) namespace (`/task/all`, `/api/account/me`); 204 = write succeeds against caller's empty namespace (`/api/account/data`); 404 = anti-enumeration opaque outcome on cross-user resource access (T-13-24). Comment block in source documents the rationale for future maintainers.
- **JWT forge branch ordering:** alg=none guard FIRST (no secret needed), then HS256 secret-required assert, then tamper post-process. Each branch is one early-return — verifier-grep `^\s+if .*\bif\b` returns 0.
- **`_seed_two_users` interface choice:** Plan's `<interfaces>` block specifies `(client_a, client_b) -> tuple[int, int]` not the PATTERNS.md alternative `(app, session_factory) -> tuple[client_a, id_a, client_b, id_b]`. Plan precedence honored — caller owns TestClient construction so each test can shape its own fixture.
- **Lazy ORMTask import inside `_insert_task`:** Module-level import would require DB engine bound at import time; lazy keeps the module loadable for plans that only need `_forge_jwt` or `_run_alembic`.

## Deviations from Plan

None — plan executed exactly as written.

The plan-level success criterion "No `pytest` references in the file" required a docstring rephrase (changed `@pytest.mark.*` mention to `test-framework decorators`) so `grep -c pytest` returns 0. This is a doc tweak inside Task 2's edit, not a deviation — the source-of-truth criterion stayed intact.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Plans 16-02..06 can now `from tests.integration._phase16_helpers import ...` without import errors. All 7 helpers + ENDPOINT_CATALOG + WS_POLICY_VIOLATION exposed and verified via standalone import test. Wave 0 complete; Wave 1 (the five parallel test plans) unblocked.

**Verification commands future plans can rerun:**
- `python -c "from tests.integration import _phase16_helpers"` — module loads
- `grep -cE "^def " tests/integration/_phase16_helpers.py` — returns 7
- `grep -c "pytest" tests/integration/_phase16_helpers.py` — returns 0

---
*Phase: 16-verification-cross-user-matrix-e2e*
*Completed: 2026-04-30*

## Self-Check: PASSED

- File exists: `tests/integration/_phase16_helpers.py` (269 lines, FOUND)
- Commit `efaeb08`: FOUND in `git log --oneline --all`
- Commit `e1a09ea`: FOUND in `git log --oneline --all`
- Plan-level verification: module loads, 7 helpers callable, 0 pytest references, ENDPOINT_CATALOG length 8
- Task 1 acceptance: 3 seeding helpers, ENDPOINT_CATALOG present, 0 nested-if
- Task 2 acceptance: 4 new helpers, total 7 def, 0 nested-if (`^\s+if .*\bif\b` count == 0)
