---
phase: 15-account-dashboard-hardening-billing-stubs
plan: 03
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, account-summary, hydration, ui-07]

# Dependency graph
requires:
  - phase: 15-01-groundwork
    provides: AccountSummaryResponse Pydantic schema in app/api/schemas/account_schemas.py
  - phase: 13-05-account-routes
    provides: AccountService base class + get_db_session + DELETE /api/account/data wiring
  - phase: 11-04-auth-services
    provides: SQLAlchemyUserRepository + IUserRepository Protocol + InvalidCredentialsError
  - phase: 13-02-dual-auth
    provides: get_authenticated_user dependency + DualAuthMiddleware + invalid_credentials_handler
provides:
  - GET /api/account/me returning AccountSummaryResponse for authenticated callers
  - AccountService.get_account_summary(user_id) — pure read of users row
  - AccountService constructor accepting IUserRepository (default lazy-construct, backward-compat with SCOPE-05 callers)
  - 3 integration tests pinning happy path + auth gate + response-shape allowlist
affects: [15-04-delete-account, 15-05-auth-hydration, 15-06-account-page]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Constructor-injected repository with default-None lazy-construct (DRT for backward compat)
    - Service returns dict shaped after Pydantic schema; route wraps via **summary
    - response_model=Schema enforces field allowlist (T-15-11 anti-leak)

key-files:
  created: []
  modified:
    - app/services/account_service.py
    - app/api/account_routes.py
    - tests/integration/test_account_routes.py

key-decisions:
  - "AccountService.__init__ accepts user_repository: IUserRepository | None — None lazy-constructs SQLAlchemyUserRepository(session), keeping every Phase-13 SCOPE-05 caller working untouched while Phase-15 callers may inject for testability"
  - "get_account_summary returns dict (not domain entity) so route can wrap via AccountSummaryResponse(**summary) — keeps service free of Pydantic dependency (SRP + framework-isolation per Phase 11 domain rules)"
  - "User-not-found surfaces as InvalidCredentialsError (→ 401 via invalid_credentials_handler) rather than 404 — anti-enumeration parity with auth failures (T-15-05); authenticated requests reaching here without a row indicate a race-condition delete, surfaced uniformly"
  - "Boundary assertion `assert user_id > 0` at service entry — tiger-style fail-loud on misuse from CLI/admin paths; HTTP path already passes positive ints from int(user.id)"
  - "Route is HTTP glue only — single line of business logic (account_service.get_account_summary); no `if`, no try/except — service-layer raises typed exceptions that flow through registered handlers"

patterns-established:
  - "Pattern: AccountSummaryResponse(**service_dict) wrapping at route boundary — keeps Pydantic out of service; mirrors Plan 13-04 KeyService → CreateKeyResponse(**dict) idiom"
  - "Pattern: lazy default-None repository injection in service constructors — preserves backward compat without forcing every existing call site to refactor"

requirements-completed: [UI-07]

# Metrics
duration: 6 min
completed: 2026-04-29
---

# Phase 15 Plan 03: Account /me Summary

**GET /api/account/me wired to AccountService.get_account_summary — server-authoritative AccountSummaryResponse hydration source for Plan 15-05 authStore.refresh() and Plan 15-06 AccountPage.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-29T19:04:41Z
- **Completed:** 2026-04-29T19:10:13Z
- **Tasks:** 2 (Task 1 atomic; Task 2 split RED+GREEN per TDD)
- **Files modified:** 3

## Accomplishments

- `AccountService.__init__` extended with optional `IUserRepository` injection (default lazy-construct) — backward compatible with all 6 existing SCOPE-05 `delete_user_data` callers
- `AccountService.get_account_summary(user_id)` — boundary-asserted, generic-error-on-miss, returns dict mirroring `AccountSummaryResponse` field names
- `GET /api/account/me` route wired with `response_model=AccountSummaryResponse` for T-15-11 field allowlist enforcement
- 3 new integration tests cover happy-path body + 401 auth gate + response-shape lockdown
- 9/9 `tests/integration/test_account_routes.py` pass (6 SCOPE-05 + 3 UI-07); Plan 15-02 logout-all suite (4/4) still green

## Task Commits

Each task was committed atomically (TDD where applicable):

1. **Task 1: Extend AccountService with user_repository + get_account_summary** — `c25c4fc` (feat)
2. **Task 2 RED: Failing /api/account/me integration tests** — `4868636` (test)
3. **Task 2 GREEN: Wire GET /api/account/me route** — `0a8b140` (feat)

**Plan metadata:** _pending — committed alongside SUMMARY/STATE/ROADMAP at end of plan_

_Note: Task 2 is a TDD task split RED → GREEN as required by `tdd="true"`._

## Files Created/Modified

- `app/services/account_service.py` — Added `IUserRepository` injection (default lazy-construct via `SQLAlchemyUserRepository(session)`); added `get_account_summary(user_id) -> dict` with tiger-style boundary assertion + generic InvalidCredentialsError on miss; preserved all existing SCOPE-05 internals untouched (`_collect_user_file_names`, `_delete_tasks_for_user`, `_delete_files`, `_unlink_safe`)
- `app/api/account_routes.py` — Added import for `AccountSummaryResponse`; added `@account_router.get("/me", response_model=AccountSummaryResponse)` route delegating to `account_service.get_account_summary` and wrapping the dict via `AccountSummaryResponse(**summary)`; existing DELETE /data route untouched
- `tests/integration/test_account_routes.py` — Appended 3 `@pytest.mark.integration` tests under a clear section header; reused existing `client`/`account_app`/`upload_dirs`/`_register` fixtures (DRY); auth-gate test mirrors the existing `test_delete_user_data_requires_auth` pattern verbatim

## Decisions Made

- **Default-None repository injection** — preserves Phase 13-05 SCOPE-05 backward compat without rewriting existing call sites (`AccountService(session=session)` in `app.api.account_routes.get_account_service`); Plan 15-04 `delete_account` will reuse the same `_user_repository` member (DRY)
- **Service returns dict, route wraps Pydantic** — keeps service free of Pydantic dependency, mirrors the established Phase 13-04 `CreateKeyResponse(**dict)` idiom; preserves SRP (service = business logic; route = HTTP glue including serialization)
- **Anti-enumeration: 401 not 404 on missing user** — T-15-05; differential 404-vs-401 between "real user, deleted by race" vs "auth failure" would leak existence; `InvalidCredentialsError` flows through the existing handler (registered in `account_app` fixture and `app/main.py`) for uniform 401 + "Authentication required" detail
- **Boundary assertion + flat guard** — single `assert user_id > 0` at service entry (fail-loud on bad caller), single `if user is None: raise` guard (no nested-if, verifier-checked grep returns 0 across both modified source files)

## Deviations from Plan

None — plan executed exactly as written. Plan 15-03 followed the prescriptive template from RESEARCH §882-925 verbatim:
- Service constructor extended with optional repository (RESEARCH §899)
- Service method body matched RESEARCH §884-896 template
- Route body matched RESEARCH §905-913 template
- 3 integration tests covered the 3 mandatory paths (happy/auth/shape) per PATTERNS

**Total deviations:** 0
**Impact on plan:** None — clean execution.

## Issues Encountered

None — no auth gates, no blockers, no architectural decisions required. Plan 15-02 was running concurrently in another agent context; verified its commits (`5e71e5e`, `5d03e77`) only touched `auth_routes.py` and `test_auth_routes.py` — zero overlap with this plan's modified files. Test isolation held (15-02 logout-all suite still 4/4 green).

## User Setup Required

None — no external service configuration required.

## Threat Flags

None — all surface introduced (`/api/account/me`) is enumerated in the plan's threat model (T-15-11 mitigated via `response_model` field allowlist; T-15-04 mitigated via `get_authenticated_user` dependency; T-15-05 mitigated via generic InvalidCredentialsError).

## Verification Results

- `pytest tests/integration/test_account_routes.py -k "get_account_me" -x -q` → **3 passed** (PASS)
- `pytest tests/integration/test_account_routes.py -k delete_user_data -q` → **6 passed** (PASS — SCOPE-05 backward compat)
- `pytest tests/integration/test_auth_routes.py -k "logout_all" -q` → **4 passed** (PASS — Plan 15-02 fixtures not clobbered)
- `grep -cE "^\s+if .*\bif\b" app/services/account_service.py` → **0** (PASS — no nested-if)
- `grep -cE "^\s+if .*\bif\b" app/api/account_routes.py` → **0** (PASS — no nested-if)
- `grep -c "def get_account_summary" app/services/account_service.py` → **1** (PASS)
- `grep -c "user_repository: IUserRepository | None = None" app/services/account_service.py` → **1** (PASS)
- `grep "assert user_id > 0" app/services/account_service.py` → present at line 83 (PASS)
- `grep -c "@account_router.get(\"/me\"" app/api/account_routes.py` → **1** (PASS)
- `grep -c "response_model=AccountSummaryResponse" app/api/account_routes.py` → **1** (PASS)
- `grep -c "account_service.get_account_summary" app/api/account_routes.py` → **1** (PASS)
- `grep -c "from app.api.schemas.account_schemas import" app/api/account_routes.py` → **1** (PASS)
- `python -c "from app.services.account_service import AccountService"` → **OK** (PASS — clean import)

All `<verification>` and `<acceptance_criteria>` checks pass.

## Success Criteria Status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | GET /api/account/me returns 200 + AccountSummaryResponse JSON for authenticated user | PASS (`test_get_account_me_returns_summary`) |
| 2 | GET /api/account/me returns 401 "Authentication required" for anonymous request | PASS (`test_get_account_me_requires_auth`) |
| 3 | AccountService(session) two-arg invocation still works for SCOPE-05 backward compat | PASS (6/6 delete_user_data tests still green) |
| 4 | AccountService(session, user_repository=...) injection works for new methods | PASS (constructor signature; integration verified via lazy-construct path in route) |
| 5 | Response body keys are exactly {user_id, email, plan_tier, trial_started_at, token_version} — no extras | PASS (`test_get_account_me_response_shape_locked`) |

## Next Phase Readiness

- **Plan 15-04 (DELETE /api/account, SCOPE-06):** Ready — can reuse `self._user_repository` already wired in the constructor; Plan 15-04 will add `delete_account(user_id)` method beside `get_account_summary`
- **Plan 15-05 (authStore.refresh hydration):** Ready — `GET /api/account/me` is the contract source of truth; frontend `accountApi.fetchAccountSummary()` from Plan 15-01 already targets `/api/account/me` and parses `AccountSummaryResponse`
- **Plan 15-06 (AccountPage):** Ready — once 15-05 wires hydration, the page can read `useAuth().user.email` instead of cookie-cached form input

No blockers. All Wave 1 plans (15-02 + 15-03) executed cleanly; Wave 2 (15-04, 15-05) unblocked.

## Self-Check: PASSED

- All 3 modified files exist on disk (`account_service.py`, `account_routes.py`, `test_account_routes.py`)
- All 3 task commits exist in git log (`c25c4fc`, `4868636`, `0a8b140`)
- All `<acceptance_criteria>` re-verified: 12/12 PASS
- Plan-level `<verification>` re-run: 13/13 PASS (includes Plan 15-02 logout-all regression check)

---
*Phase: 15-account-dashboard-hardening-billing-stubs*
*Completed: 2026-04-29*
