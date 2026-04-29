---
phase: 15
plan: 01
subsystem: account
tags: [groundwork, dry, schemas, msw, apiClient]
requires:
  - apiClient.request() supports body+suppress401Redirect on every method (Phase 14-02)
  - app/api/auth_routes.py /logout pattern (Phase 13-03)
  - frontend MSW barrel (Phase 14-01)
provides:
  - apiClient.get accepts {headers, suppress401Redirect}
  - apiClient.delete accepts optional JSON body
  - app.api._cookie_helpers.clear_auth_cookies (shared)
  - app.api.schemas.account_schemas.AccountSummaryResponse + DeleteAccountRequest
  - frontend accountApi.ts (4 typed wrappers)
  - MSW account.handlers.ts spread into barrel
affects:
  - app/api/auth_routes.py (now imports clear_auth_cookies)
  - frontend/src/tests/lib/apiClient.test.ts (4 new tests)
tech-stack:
  added: []
  patterns:
    - "Public exports object owns API surface (apiClient.ts) — internal request() unchanged"
    - "Pydantic v2 EmailStr field allowlist (T-15-11 mitigation)"
    - "Shared cookie-clearing helper across auth + account routes (DRY)"
key-files:
  created:
    - app/api/_cookie_helpers.py
    - app/api/schemas/account_schemas.py
    - frontend/src/lib/api/accountApi.ts
    - frontend/src/tests/msw/account.handlers.ts
    - tests/unit/api/test_cookie_helpers.py
  modified:
    - frontend/src/lib/apiClient.ts
    - frontend/src/tests/lib/apiClient.test.ts
    - app/api/auth_routes.py
    - frontend/src/tests/msw/handlers.ts
key-decisions:
  - "apiClient.get migrated from headers-only signature to {headers, suppress401Redirect} opts object — opts pattern matches existing post()"
  - "clear_auth_cookies dropped its leading underscore (now public) since it crosses module boundaries; SESSION_COOKIE/CSRF_COOKIE constants moved with it as the single source of truth"
  - "account_schemas.py uses Pydantic v2 EmailStr field allowlist — only {user_id, email, plan_tier, trial_started_at, token_version} cross the wire (T-15-11)"
  - "submitUpgradeInterest() left bare (no try/catch) — caller in UpgradeInterestDialog (Wave 2) catches ApiClientError statusCode===501 as success per T-15-07"
requirements-completed: [UI-07, AUTH-06, SCOPE-06, BILL-05, BILL-06]
duration: 9 min
completed: 2026-04-29
---

# Phase 15 Plan 01: Wave 0 Groundwork Summary

Wave 0 wiring substrate — apiClient signature extensions, shared `clear_auth_cookies` helper, Pydantic schemas, frontend `accountApi` module, and MSW account handlers. Zero business logic; pure DRY scaffolding that unblocks Waves 1-3.

## Execution

- **Start:** 2026-04-29T18:51:25Z
- **End:** 2026-04-29T19:00:24Z
- **Duration:** ~9 min
- **Tasks completed:** 3 / 3
- **Files created:** 5
- **Files modified:** 4
- **Commits:** 5 atomic (3 GREEN feat + 2 RED test)

## Task Breakdown

### Task 1 — Extend apiClient.get + delete signatures (TDD)

- **RED commit:** `309bc1b` — 4 failing tests written for `{suppress401Redirect}`/`{headers}` GET options + DELETE body forwarding
- **GREEN commit:** `c9d8896` — public exports object updated; internal `request()` untouched; 14/14 apiClient tests pass; tsc green

### Task 2 — Extract clear_auth_cookies (TDD)

- **RED commit:** `ec79c98` — `tests/unit/api/test_cookie_helpers.py` written; fails with `ModuleNotFoundError`
- **GREEN commit:** `9f7d041` — `app/api/_cookie_helpers.py` created (24 LOC); `auth_routes.py` migrated to import the shared helper, `_clear_auth_cookies` deleted, `SESSION_COOKIE`/`CSRF_COOKIE` constants relocated; 12/12 auth_routes integration tests still pass

### Task 3 — Schemas + accountApi.ts + MSW handlers + barrel

- **Commit:** `7c39712` — `account_schemas.py` (AccountSummaryResponse + DeleteAccountRequest), `accountApi.ts` (fetchAccountSummary/logoutAllDevices/deleteAccount/submitUpgradeInterest), `account.handlers.ts` (4 endpoints), `handlers.ts` barrel updated; 61/61 vitest tests pass; schemas instantiate via python smoke

No separate RED commit for Task 3 because the plan explicitly states *"No tests created in this task — Wave 1+ tasks consume these mocks."* The gate is the verifier-grep acceptance criteria block (all 13 grep checks passed) plus tsc + python instantiation smoke.

## Verification Results

| Gate | Command | Result |
|------|---------|--------|
| apiClient tests | `bun run vitest run src/tests/lib/apiClient.test.ts` | 14/14 PASS |
| Cookie helper unit | `pytest tests/unit/api/test_cookie_helpers.py` | 2/2 PASS |
| auth_routes regression | `pytest tests/integration/test_auth_routes.py` | 12/12 PASS |
| Schema smoke | `python -c "from app.api.schemas.account_schemas import ..."` | OK |
| TypeScript | `bunx tsc --noEmit` | exit 0 |
| Full vitest suite | `bun run vitest run` | 61/61 PASS |
| nested-if invariant | `grep -cE "^\s+if .*\bif\b"` (4 new/modified files) | 0 / 0 / 0 / 0 |
| BILL-06 stub presence | `grep -q /webhook \| Stripe-Signature \| 501 app/api/billing_routes.py` | 3/3 OK |

## Acceptance Criteria

All 24 grep/runtime acceptance criteria across the 3 tasks PASS. One technically off-by-one notation:

- **Task 3 AC4** asks `grep -c "EmailStr" app/api/schemas/account_schemas.py` returns 2 (one per schema). Actual count is 3 (1 import + 2 field annotations). The intent — "one EmailStr field per schema" — is satisfied; the count just includes the import line. Matches the analog `auth_schemas.py` pattern verbatim (also 3). Treated as PASS.

## Deviations from Plan

None - plan executed exactly as written.

## Threat Mitigations Landed

- **T-15-08** (apiClient.delete missing body) — mitigated: signature extended; tsc enforces caller correctness.
- **T-15-11** (Schema serialization leaks) — mitigated: Pydantic field allowlist in `AccountSummaryResponse` exposes only id/email/plan_tier/trial_started_at/token_version.
- **T-15-04** (Cookie-clearing anti-pattern documentation) — partial: `clear_auth_cookies` docstring documents the "construct a fresh Response" rule. Wave 1+ verifier-grep will enforce on call sites.
- **T-15-07** (501 swallow as success) — documented in `accountApi.ts.submitUpgradeInterest` JSDoc; consumer `UpgradeInterestDialog` (Wave 2) implements the catch.

## Threat Flags

(none — no new attack surface introduced; only typed wiring + DRY refactor)

## Authentication Gates

(none — pure local development work)

## Known Stubs

- `submitUpgradeInterest` POSTs `/billing/checkout` which returns 501 in v1.2 (BILL-05). Stub deliberate per CONTEXT §145; Stripe Checkout integration deferred to v1.3 (FUTURE-01).
- `/billing/webhook` 501 stub already present from Phase 13-05 (BILL-06); not modified here.

These are documented and intentional — Phase 15 only **wires UI to existing stubs**.

## Next Step

Ready for **Plan 15-02** (Wave 1 — backend `/api/account/me` route + AccountService.get_account_summary).

## Self-Check: PASSED

**Files exist:**
- app/api/_cookie_helpers.py — FOUND
- app/api/schemas/account_schemas.py — FOUND
- frontend/src/lib/api/accountApi.ts — FOUND
- frontend/src/tests/msw/account.handlers.ts — FOUND
- tests/unit/api/test_cookie_helpers.py — FOUND

**Commits exist (`git log --oneline | grep <hash>`):**
- 309bc1b `test(15-01): add failing tests for apiClient.get(opts) + apiClient.delete(body)` — FOUND
- c9d8896 `feat(15-01): apiClient.get accepts opts; apiClient.delete accepts body` — FOUND
- ec79c98 `test(15-01): add failing tests for app.api._cookie_helpers` — FOUND
- 9f7d041 `feat(15-01): extract clear_auth_cookies to app.api._cookie_helpers` — FOUND
- 7c39712 `feat(15-01): account_schemas + accountApi + MSW account handlers` — FOUND

**TDD gate compliance:**
- Task 1: RED (`309bc1b`) → GREEN (`c9d8896`) — sequence valid
- Task 2: RED (`ec79c98`) → GREEN (`9f7d041`) — sequence valid
- Task 3: declared no-test by plan; verified via grep + tsc + python smoke (compliant)
