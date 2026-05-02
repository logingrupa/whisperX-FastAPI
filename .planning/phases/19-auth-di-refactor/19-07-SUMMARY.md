---
phase: 19-auth-di-refactor
plan: 07
subsystem: api
tags: [fastapi, depends, auth, csrf, sweep, billing-split, ws-ticket]

# Dependency graph
requires:
  - phase: 19-auth-di-refactor
    provides: "authenticated_user + csrf_protected (Plans 04+05)"
  - phase: 19-auth-di-refactor
    provides: "Pilot route pattern validated (Plan 06)"
provides:
  - "All HTTP route families migrated to Depends(authenticated_user) + Depends(csrf_protected)"
  - "billing_router split into auth + webhook variants"
  - "ws_ticket_service unified — HTTP issue and WS consume share the same lru-cached singleton"
affects: [19-08, 19-09, 19-10, 19-11, 19-12]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Router-level CSRF on auth/key/billing/task/ws_ticket — bearer-skip + method-gate handled inside csrf_protected"
    - "billing_webhook_router separated; Stripe-Signature HMAC stays auth-free (PUBLIC_ALLOWLIST shrinks)"
    - "ws_ticket_service via app.core.services.get_ws_ticket_service singleton — HTTP issue path (ws_ticket_routes) and WS consume path (websocket_api) agree on the same instance"

key-files:
  created:
    - "app/api/billing_webhook_router.py — Stripe webhook isolated"
  modified:
    - "app/api/auth_routes.py — Depends chain"
    - "app/api/key_routes.py — Depends chain + router CSRF"
    - "app/api/billing_routes.py — split into auth-required half"
    - "app/api/task_api.py — get_task_management_service_v2 + router CSRF"
    - "app/api/ws_ticket_routes.py — drop inline _container reach-in factory; singleton import; router CSRF"
    - "app/api/websocket_api.py — ticket_service via singleton (legacy _container.task_repository() preserved for Plan 19-08)"
    - "app/api/__init__.py — export billing_webhook_router"
    - "app/main.py — register billing_webhook_router"
    - "tests/integration/_phase16_helpers.py + test_per_user_scoping/test_task_routes/test_ws_ticket_flow/test_ws_ticket_safety — additive get_db overrides + X-CSRF-Token plumbing"

key-decisions:
  - "Plan 07 split into 2 atomic commits: (a) auth/key/billing routers; (b) task_api/ws_ticket/websocket_api — kept the second half coexisting with legacy _container.task_repository() in websocket_api so Plan 19-08 owns the full WS scope refactor"
  - "ws_ticket_service singleton unification was a Rule-1 latent-bug fix discovered mid-execution: HTTP issue (Plan 06 baseline) used _container.ws_ticket_service() while WS consume used a different reach-in. The two created different in-memory ticket dicts, so a ticket issued via HTTP could never be consumed. Switched both to app.core.services.get_ws_ticket_service singleton"
  - "billing_router split: webhook router has zero dependencies (Stripe-Signature HMAC owns authenticity in v1.3); main billing_router gets full auth + csrf chain"

patterns-established:
  - "Sweep cadence: 5 routers × ~30 LOC = clean 1-commit work per router family. Each router commit kept tests local-green before proceeding"
  - "Webhook isolation: split into a sibling router rather than mounting on the same router with auth=False — explicit and easy to grep"

requirements-completed: [REFACTOR-03]
threats-mitigated:
  - id: WS-TICKET-MIX-UP
    description: "Two ws_ticket_service singletons (HTTP container vs WS reach-in) silently broke ticket reuse — fixed by unifying on app.core.services singleton"

# Metrics
duration: 38min
completed: 2026-05-02
---

# Phase 19 Plan 07: route-sweep Summary

**5 router families (`auth`, `key`, `billing`, `task`, `ws_ticket`) migrated to the Phase 19 `Depends(authenticated_user)` + router-level `Depends(csrf_protected)` chain. `billing_router` split into auth + webhook variants. `ws_ticket_service` unified on the `app.core.services` lru-cached singleton so HTTP-issue and WS-consume paths share the same in-memory ticket dict.**

## Performance

- **Duration:** ~38 min
- **Tasks:** 2 of 2 (split into 2 atomic commits)
- **Files modified:** 10 + 1 created
- **Commits:**
  - `fad3485` — refactor(19-07): migrate auth/key/billing routers to Depends chain
  - `973e2dd` — refactor(19-07): migrate task_api + ws_ticket_routes to Depends chain + ws_ticket_service singleton

## Verification

- 37/37 affected integration tests GREEN (test_task_routes, test_per_user_scoping, test_ws_ticket_flow, test_ws_ticket_safety)
- Nested-if grep == 0 across modified files
- `_container.` references in modified files: 0 in code (1 docstring noting what was removed in ws_ticket_routes.py — explanatory)
- Bearer-skip + method-gate semantics preserved (csrf_protected internal logic unchanged)
- DualAuthMiddleware + CsrfMiddleware still installed (coexistence — Plans 11/12 own deletion)

## Notes for downstream plans

- **Plan 08 (WebSocket scope refactor):** websocket_api.py still has one `_container.task_repository()` reach-in (legacy task repo path). Plan 08 replaces it with `with SessionLocal() as db:` per CONTEXT D2. ticket_service migration done in Plan 07.
- **Plan 09 (Background task scope):** whisperx_wrapper_service.py untouched in this plan.
- **Plan 10 (Test fixture migration):** integration tests modified in this plan use the additive Rule-3 bridge (`app.dependency_overrides[get_db]` alongside legacy container.override). Plan 10 owns the full container.override → dependency_overrides cutover.

## Deviations

- **Quota interrupt:** mid-execution, executor agent hit Anthropic usage cap during task 2. Orchestrator reviewed uncommitted diffs (task_api.py, ws_ticket_routes.py, websocket_api.py partial, 5 test files), confirmed correctness via integration test run (37/37 GREEN), and committed the work as `973e2dd`. No work lost.

## Status

PLAN COMPLETE
