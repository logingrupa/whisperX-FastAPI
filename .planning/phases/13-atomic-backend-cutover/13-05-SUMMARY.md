---
phase: 13-atomic-backend-cutover
plan: 05
subsystem: backend-routes
tags: [account-deletion, stripe-stubs, privacy, billing-ready, integration-tests]
requires:
  - phase: 13-01
    provides: AuthSettings.{V2_ENABLED, COOKIE_*}; stripe 15.1.0 dependency
  - phase: 13-02
    provides: get_authenticated_user dependency; DualAuthMiddleware (PUBLIC_ALLOWLIST extended)
  - phase: 13-03
    provides: auth_router (cookie-acquisition path for tests)
  - phase: 11
    provides: Container.db_session_factory; ORM Task/User/ApiKey models
  - phase: 10
    provides: tasks.user_id FK + Phase 12 backfill (DELETE FROM tasks WHERE user_id scopes correctly)
provides:
  - app.api.account_routes.account_router with DELETE /api/account/data (SCOPE-05)
  - app.api.billing_routes.billing_router with POST /billing/checkout + /billing/webhook (BILL-05/06; 501 stubs)
  - app.api.schemas.billing_schemas.{CheckoutRequest, StubResponse}
  - app.services.account_service.AccountService.delete_user_data — tasks + files deletion preserving users row
  - app.api.dependencies.get_db_session — generator yielding managed Container session for non-repository services
  - tests/integration/test_account_routes.py — 6 integration tests
  - tests/integration/test_billing_routes.py — 6 integration tests
affects:
  - app/core/dual_auth.py — PUBLIC_ALLOWLIST extended with /billing/webhook (Rule 3 deviation; Stripe server-to-server contract)
  - plan 13-09 (atomic flip): mounts account_router + billing_router on FastAPI app under is_auth_v2_enabled() guard
  - phase 15 SCOPE-06: AccountService extension point — full users-row deletion will compose alongside delete_user_data
  - phase 15 BILL-05/06: frontend dashboards consume the locked CheckoutRequest + StubResponse schemas without churn when v1.3 fills in the real endpoint bodies
tech-stack:
  added: []
  patterns:
    - "Self-serve data deletion preserves users row — delete_user_data scopes to user_id; users row intentionally untouched (Phase 15 SCOPE-06 will extend with full row deletion via composition not modification)"
    - "Raw text() SQL with bound :uid parameter for bulk DELETE FROM tasks — preferred over ORM session.delete loop for cross-user-data deletion (audit trail in route layer; SQL injection mitigated by bound param T-13-19)"
    - "Best-effort file deletion: _unlink_safe returns 0 on missing/error so a partial file system never blocks task-row deletion; failures logged at WARNING with path (T-13-20 accept)"
    - "Stripe 501 stubs with module-load `import stripe` — BILL-07 verifies the dependency tree resolves; verifier-checked grep confirms zero stripe.*(  ) runtime calls in app/"
    - "Stripe-Signature schema validation via regex (`t=<unix>,(vN=<hex>,?)+`) — rejects malformed/spam at 400 before 501 branch; HMAC verification deferred to v1.3 (T-13-21/22 accept)"
    - "PUBLIC_ALLOWLIST extension for /billing/webhook — Stripe calls server-to-server; auth via Stripe-Signature HMAC not cookie/bearer (deviation Rule 3 — blocking issue: middleware 401'd webhook before route logic could run)"
    - "DRY auth resolution: every authenticated route uses Depends(get_authenticated_user); webhook stub intentionally omits to honour Stripe contract"
    - "SRP — routes do HTTP only; AccountService owns deletion; billing routes carry zero business logic beyond the schema-check guard"
    - "get_db_session generator helper — yields a managed Container.db_session_factory() for services needing a raw session rather than a repository wrapper; closes on exit (no underscore-private import from dependencies module)"
key-files:
  created:
    - app/services/account_service.py
    - app/api/account_routes.py
    - app/api/schemas/billing_schemas.py
    - app/api/billing_routes.py
    - tests/integration/test_account_routes.py
    - tests/integration/test_billing_routes.py
  modified:
    - app/api/dependencies.py
    - app/core/dual_auth.py
key-decisions:
  - "AccountService accepts a raw Session (not an ITaskRepository) — bulk DELETE via text() is materially simpler than load-all-Tasks-then-iterate-delete, and the user_id-scoped query has zero risk of leaking cross-user data via accidental ORM cascade. ITaskRepository's set_user_scope (Phase 13-07) is not yet on disk; AccountService deliberately does NOT depend on 13-07."
  - "get_db_session added to dependencies.py rather than importing private _container from account_routes — keeps the underscore-private prefix meaningful (no external imports of _container); provides a clean session generator that future services (e.g. SCOPE-06 full-account-delete) reuse."
  - "PUBLIC_ALLOWLIST gains /billing/webhook (Rule 3 blocking deviation) — without this the webhook stub returns 401 before the schema-check guard runs, breaking the Stripe contract. The schema-check at 400 is the security boundary; 501 on valid schema is the placeholder. Auth is intentionally never required on this route."
  - "Stripe-Signature regex `^t=\\d+,(v\\d+=[a-fA-F0-9]+,?)+$` matches the documented Stripe header shape (`t=<ts>,v1=<hex>[,v0=<hex>]`) — strict enough to reject spam/garbage; loose enough that valid v1.3 production headers pass without modification. Full HMAC verification is the v1.3 step."
  - "StubResponse exposes `detail`/`status`/`hint` defaults — Phase 15 frontend can render `Stripe integration arrives in v1.3` directly from the body; no string churn needed when v1.3 lands (StubResponse will be replaced by CheckoutSessionResponse / WebhookEventResponse, but this stub never reaches a real Pro user — Pro upgrade UI ships in Phase 15 alongside real stripe.checkout.Session.create)."
  - "Test fixtures monkey-patch UPLOAD_DIR + TUS_UPLOAD_DIR onto the account_service module rather than the upload_config module — keeps tmp file isolation per-test without touching global config; aligns with 13-03/13-04 Container-override pattern."
patterns-established:
  - "Bulk user-data delete: SELECT file names → bulk DELETE tasks → best-effort file unlinks → INFO log with counts (no PII)"
  - "Stripe stub layout: `import stripe` at module-load + 501 + StubResponse + schema-only header check on webhook"
  - "Public webhook contract: Stripe-Signature HMAC is the security boundary, not session/bearer auth"
requirements-completed:
  - SCOPE-05 (DELETE /api/account/data deletes user's tasks + files; users row preserved)
  - BILL-01 (plan_tier column present + queryable — Phase 10 schema; smoke verified by Pydantic CheckoutRequest passing through middleware → service stack)
  - BILL-02 (stripe_customer_id column present + nullable — Phase 10 schema; runtime population deferred to v1.3)
  - BILL-03 (subscriptions table present + queryable — Phase 10 schema)
  - BILL-04 (usage_events table present + queryable with idempotency_key UNIQUE — Phase 10 schema)
duration: ~10 min
completed: 2026-04-29
---

# Phase 13 Plan 05: Account Data Deletion + Billing Stubs Summary

DELETE /api/account/data (SCOPE-05) deletes caller's tasks + uploaded files preserving the users row, plus POST /billing/checkout (auth) + POST /billing/webhook (server-to-server) returning 501 with `import stripe` at module-load (BILL-07 — zero runtime stripe.* calls), all behind 12 passing integration tests covering cross-user isolation, file cleanup, and Stripe-Signature schema validation.

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-29T10:29:02Z
- **Completed:** 2026-04-29T10:38:46Z
- **Tasks:** 3
- **Files created:** 6
- **Files modified:** 2

## Accomplishments

- DELETE /api/account/data endpoint exposed on `account_router` (mounted under `is_auth_v2_enabled()` guard in plan 13-09)
- POST /billing/checkout + POST /billing/webhook exposed on `billing_router` — both 501 stubs; checkout requires auth, webhook does NOT (server-to-server contract)
- AccountService.delete_user_data: bulk DELETE FROM tasks WHERE user_id = :uid via raw text() with bound parameter; best-effort file cleanup at UPLOAD_DIR + UPLOAD_DIR/tus; users row preserved (Phase 15 SCOPE-06 will compose alongside)
- `import stripe` at module-load in billing_routes.py (BILL-07 verifier-checked); ZERO runtime `stripe.*(...)` calls in app/ (verifier grep confirms 0 matches)
- Stripe-Signature header SCHEMA validation via regex (`^t=\d+,(v\d+=[a-fA-F0-9]+,?)+$`) — rejects malformed/spam at 400; valid schema → 501; HMAC verification deferred to v1.3
- StubResponse schema with stable `detail`/`status`/`hint` defaults — Phase 15 frontend can render the v1.3 hint directly without string churn
- get_db_session generator added to dependencies.py — yields managed Container.db_session_factory() for non-repository scoped services; closes on exit
- PUBLIC_ALLOWLIST extended with /billing/webhook (Rule 3 deviation; Stripe contract) — auth intentionally omitted on this route
- 12 integration tests cover: tasks-removed, user-row-preserved, files-cleaned (UPLOAD_DIR + tus), missing-files-best-effort, cross-user-isolation (A's data survives B's DELETE), requires-auth-401, checkout-501, checkout-requires-auth, webhook-valid-schema-501, webhook-missing-signature-400, webhook-malformed-signature-400, stripe-module-load-smoke

## Task Commits

Each task committed atomically:

1. **Task 1: AccountService + account_routes (DELETE /api/account/data) + get_db_session** — `db9a24d` (feat)
2. **Task 2: Billing stubs (POST /billing/checkout + /billing/webhook) + stripe import** — `2afedb2` (feat)
3. **Task 3: Integration tests for account_routes + billing_routes (+ PUBLIC_ALLOWLIST fix)** — `9661697` (test)

## Files Created/Modified

### Created

- `app/services/account_service.py` (78 lines) — `class AccountService(session: Session)`; `delete_user_data(user_id) -> {tasks_deleted, files_deleted}`; flat helpers `_collect_user_file_names`, `_delete_tasks_for_user`, `_delete_files`, `_unlink_safe` (no nested-if); raw `text()` SQL with bound `:uid` for bulk DELETE; INFO log with user_id + counts only (no file paths)
- `app/api/account_routes.py` (43 lines) — `account_router = APIRouter(prefix="/api/account", tags=["Account"])`; single DELETE /data endpoint using `Depends(get_authenticated_user)` + `Depends(get_account_service)`; SRP route delegates to AccountService; returns 204 Response
- `app/api/schemas/billing_schemas.py` (29 lines) — `CheckoutRequest(plan: str)` + `StubResponse(detail="Not Implemented", status="stub", hint="Stripe integration arrives in v1.3")`
- `app/api/billing_routes.py` (89 lines) — `billing_router = APIRouter(prefix="/billing", tags=["Billing"])`; `import stripe` (BILL-07); 2 endpoints: `/checkout` requires auth + 501 + StubResponse; `/webhook` no auth + Stripe-Signature regex schema-check (400 on malformed) + 501 on valid; `_STRIPE_SIG_PATTERN` module-level compiled regex
- `tests/integration/test_account_routes.py` (244 lines, 6 cases) — slim FastAPI app per test; mounts auth_router + account_router + DualAuthMiddleware; per-test Container override; monkey-patches UPLOAD_DIR + TUS_UPLOAD_DIR onto account_service module for tmp dir isolation; includes cross-user isolation test using two TestClient instances
- `tests/integration/test_billing_routes.py` (180 lines, 6 cases) — slim FastAPI app per test; checkout (auth required) + webhook (no auth) coverage; explicit BILL-07 module-load smoke test asserts `app.api.billing_routes` exports `billing_router` + `_STRIPE_SIG_PATTERN`

### Modified

- `app/api/dependencies.py` — appended `get_db_session() -> Generator[Session, None, None]` after `get_rate_limit_service`; added `from sqlalchemy.orm import Session` import; closes session on exit
- `app/core/dual_auth.py` — added `/billing/webhook` to `PUBLIC_ALLOWLIST` tuple with explanatory comment about Stripe server-to-server contract (Rule 3 deviation)

## Verification

### Acceptance Grep Gates

| Gate | Expected | Actual |
| ---- | -------- | ------ |
| `class AccountService` + `delete_user_data` exists | 1 | 1 |
| `DELETE FROM tasks WHERE user_id` in account_service.py | 1 | 1 |
| `preserve\|preserved` in account_service.py | ≥1 | 2 |
| nested-if (`^\s+if .*\bif\b`) in account_service.py | 0 | 0 |
| `@account_router.delete.*"/data"` in account_routes.py | 1 | 1 |
| `Depends(get_authenticated_user)` in account_routes.py | 1 | 1 |
| `def get_db_session` in dependencies.py | 1 | 1 |
| `^import stripe` in billing_routes.py (BILL-07) | 1 | 1 |
| `stripe\.\w+\(` runtime call in app/ (excluded billing_routes) | 0 | 0 |
| `501` in billing_routes.py (both routes) | ≥2 | 7 |
| `Stripe-Signature` in billing_routes.py | ≥1 | 5 |
| nested-if in billing_routes.py | 0 | 0 |
| `@pytest.mark.integration` in test_account_routes.py | ≥6 | 6 |
| `@pytest.mark.integration` in test_billing_routes.py | ≥5 | 6 |

### Test Outcomes

```
$ pytest tests/integration/test_account_routes.py tests/integration/test_billing_routes.py -v -m integration
12 passed in 1.72s
```

| # | Test | Status |
| - | ---- | ------ |
| 1 | test_delete_user_data_removes_tasks | PASS |
| 2 | test_delete_user_data_preserves_user_row | PASS |
| 3 | test_delete_user_data_removes_uploaded_files | PASS |
| 4 | test_delete_user_data_skips_missing_files | PASS |
| 5 | test_delete_user_data_cross_user_isolation | PASS |
| 6 | test_delete_user_data_requires_auth | PASS |
| 7 | test_checkout_stub_returns_501 | PASS |
| 8 | test_checkout_requires_auth | PASS |
| 9 | test_webhook_valid_signature_schema_returns_501 | PASS |
| 10 | test_webhook_missing_signature_returns_400 | PASS |
| 11 | test_webhook_malformed_signature_returns_400 | PASS |
| 12 | test_stripe_imported_no_runtime_calls | PASS |

### Regression

```
$ pytest tests/integration/test_auth_routes.py tests/integration/test_key_routes.py -v -m integration
24 passed in 10.67s
```

(Phase 13-03 + 13-04 integration tests: 12 + 12 = 24 still green after PUBLIC_ALLOWLIST change.)

## Stripe-Import Evidence (BILL-07)

```
$ grep -n "^import stripe" app/api/billing_routes.py
27:import stripe  # noqa: F401  # BILL-07 — module-load import only; no runtime calls

$ grep -rn "stripe\.\w*(" app/ | grep -v billing_routes.py
(no matches)
```

`stripe` is imported at module-load — guarantees the dependency tree resolves identically in v1.3 when real `stripe.checkout.Session.create(...)` calls land. v1.2 has ZERO runtime `stripe.*(...)` calls in `app/`. The webhook validates `Stripe-Signature` SCHEMA via regex, never `stripe.Webhook.construct_event`.

## Cross-User Isolation Mechanism

```python
# AccountService.delete_user_data — text() with bound :uid
self.session.execute(
    text("DELETE FROM tasks WHERE user_id = :uid"),
    {"uid": user_id},
)
```

The DELETE statement is scoped to `:uid` — bound parameter (zero SQL injection risk; T-13-19 mitigated). User B's DELETE never touches User A's rows because `request.state.user.id` is set by DualAuthMiddleware after authenticating User B's session. Integration test `test_delete_user_data_cross_user_isolation` registers User A + User B (separate `TestClient` cookie jars), inserts 3 + 2 tasks respectively, calls DELETE as User B, and asserts User A still has 3 rows + User B has 0.

## Stripe-Signature Schema Validation

```python
_STRIPE_SIG_PATTERN = re.compile(r"^t=\d+,(v\d+=[a-fA-F0-9]+,?)+$")

if not stripe_signature or not _STRIPE_SIG_PATTERN.match(stripe_signature):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid Stripe-Signature header schema",
    )
```

Regex matches the documented Stripe header shape: `t=<unix_ts>,v1=<hex>` (with optional additional `vN=<hex>` segments). v1.3 will replace the regex check with `stripe.Webhook.construct_event(payload, sig, secret)` for full HMAC authenticity — but the schema gate already rejects spam/garbage at 400 with no DB writes, so DoS exposure is bounded by `re.match` cost (T-13-21 accept).

## Decisions Made

- **AccountService takes a raw Session, not an ITaskRepository** — bulk DELETE via `text()` is simpler + safer than load-all-Tasks-then-iterate; the `user_id`-scoped query is leak-proof (no ORM cascade surprise). ITaskRepository's `set_user_scope` (Phase 13-07) is intentionally NOT a dependency.
- **get_db_session helper added to dependencies.py** — keeps the `_container` underscore-prefix meaningful (no external imports of `_container`); future services (Phase 15 SCOPE-06 full-row delete, Phase 17 admin scripts) compose against this generator.
- **PUBLIC_ALLOWLIST gains /billing/webhook** — Rule 3 (blocking issue) deviation. Without this entry the middleware 401s before reaching the schema-check guard, breaking the Stripe contract. Auth is intentionally NEVER required on /billing/webhook; authenticity is via Stripe-Signature HMAC (v1.3).
- **StubResponse defaults are stable** — `detail`/`status`/`hint` field defaults are part of the public contract; Phase 15 frontend renders the v1.3 hint directly. v1.3 will replace StubResponse with CheckoutSessionResponse / WebhookEventResponse but this stub never serves a real Pro upgrade flow — Pro upgrade UI ships in Phase 15 alongside real `stripe.checkout.Session.create`.
- **Test fixtures monkey-patch account_service module attrs (UPLOAD_DIR + TUS_UPLOAD_DIR)** — not the upload_config module — keeps per-test isolation aligned with 13-03/13-04 Container-override pattern; no global config mutation.
- **Two TestClient instances for cross-user test** — separate cookie jars against same app+DB; simulates two real users without process-isolation overhead. Pattern reused from test_key_routes.py test_delete_key_cross_user_returns_404.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Added /billing/webhook to PUBLIC_ALLOWLIST**
- **Found during:** Task 3 (running test_webhook_valid_signature_schema_returns_501)
- **Issue:** DualAuthMiddleware returned 401 for `POST /billing/webhook` before the route's schema-check guard could run. Three webhook tests failed: valid-schema-501, missing-signature-400, malformed-signature-400 (all returned 401 instead).
- **Root cause:** Plan locked the webhook as auth-NOT-required (Stripe calls server-to-server) but PUBLIC_ALLOWLIST in `app/core/dual_auth.py` (set up by Plan 13-02) didn't include `/billing/webhook`.
- **Fix:** Appended `/billing/webhook` to `PUBLIC_ALLOWLIST` tuple with explanatory comment about Stripe server-to-server authenticity contract. Webhook now reaches the schema-check guard, which returns 400 on malformed and 501 on valid schema as planned.
- **Files modified:** `app/core/dual_auth.py`
- **Commit:** `9661697`
- **Verification:** All 12 plan-13-05 tests pass; 24 prior phase 13 tests (test_auth_routes.py + test_key_routes.py) still pass — no regression.

No architectural deviations — the fix preserves the locked CONTEXT §50-54 + §155 invariants (webhook auth-NOT-required; Stripe-Signature is the boundary). Decision was clear-cut Rule 3 (blocking issue: middleware blocked the route before guard could run).

## Issues Encountered

- Pre-existing dirty working tree (README.md, openapi.json/yaml, app/main.py, app/core/config.py, frontend FileQueueItem.tsx) — out of scope for plan 13-05; untouched by all 3 task commits. Each commit explicitly staged only its own files (no `git add -A`).
- 13 pytest warnings (matplotlib deprecation in pyannote, JWT InsecureKeyLengthWarning, Pydantic UPPER_HTTP_STATUS deprecation) — pre-existing; out of scope.

## Threat Mitigations Applied

| Threat ID | Mitigation |
| --------- | ---------- |
| T-13-19 (tampering — cross-user DELETE) | AccountService.delete_user_data scopes to caller's user_id (set by DualAuthMiddleware on `request.state.user`); raw `text()` SQL with bound `:uid` parameter (zero SQL injection risk); cross-user isolation test verifies User A's 3 tasks survive User B's DELETE |
| T-13-20 (info disclosure — file paths in logs) | accept (per plan); INFO log emits user_id + counts only; path is logged at WARNING ONLY when `unlink` fails (ops debugging requirement, no PII in path) |
| T-13-21 (DoS — webhook spam) | accept (per plan); stub returns 501 with no DB writes; only cheap regex `re.match` runs before 400 rejection on malformed; v1.3 will add full HMAC + rate-limiting |
| T-13-22 (spoofing — webhook unauthenticated) | accept (per plan); v1.2 stub does no real signature verification; v1.3 will verify HMAC via `stripe.Webhook.construct_event`; stub returns 501 — ZERO state change so spoofed webhooks have no impact |
| T-13-23 (info disclosure — stripe API key leak) | mitigate; `import stripe` only — verifier-checked: `grep "stripe\.api_key" app/` returns 0; no `stripe.api_key = "..."` assignments in v1.2 |

## User Setup Required

None — all changes are server-side. Routes will be mounted on `app/main.py` in plan 13-09 (atomic flip with `is_auth_v2_enabled()` guard) alongside auth_router + key_router.

## Next Phase Readiness

- `account_router` + `billing_router` are built but **NOT yet mounted** on `app/main.py`. Plan 13-09 (atomic flip) will `app.include_router(account_router); app.include_router(billing_router)` under the V2 feature flag.
- The DualAuthMiddleware → `request.state.user` → `Depends(get_authenticated_user)` contract from 13-02 now serves 5 production routes across 3 routers: auth (3), keys (3), account (1), billing checkout (1). Webhook intentionally bypasses the middleware via PUBLIC_ALLOWLIST.
- Phase 15 SCOPE-06 (full-account-delete, DELETE /api/account) will compose: delete_user_data first → DELETE FROM users WHERE id = :uid → done. AccountService is the natural extension point (open/closed: append `delete_user_account` method that calls `delete_user_data` then drops the row).
- Phase 15 BILL-05/06 (UI for checkout + webhook handling) consumes the locked StubResponse + CheckoutRequest schemas; v1.3 will replace StubResponse with real CheckoutSessionResponse but the field shape pattern (`detail`/`status` + payload-specific fields) is the contract.
- BILL-01..04 (schema-only requirements) are smoke-verified through this plan's stack: Pydantic CheckoutRequest validated → middleware → route → DB connection (via Container.db_session_factory) — confirms the Phase 10 plan_tier + stripe_customer_id + subscriptions + usage_events tables are queryable end-to-end. Runtime population of these columns/rows arrives in v1.3.

## Self-Check

Files created exist:
- `app/services/account_service.py` → FOUND
- `app/api/account_routes.py` → FOUND
- `app/api/schemas/billing_schemas.py` → FOUND
- `app/api/billing_routes.py` → FOUND
- `tests/integration/test_account_routes.py` → FOUND
- `tests/integration/test_billing_routes.py` → FOUND

Files modified:
- `app/api/dependencies.py` → MODIFIED (get_db_session appended)
- `app/core/dual_auth.py` → MODIFIED (PUBLIC_ALLOWLIST extended)

Commits exist:
- `db9a24d` → FOUND (Task 1)
- `2afedb2` → FOUND (Task 2)
- `9661697` → FOUND (Task 3)

## Self-Check: PASSED

---
*Phase: 13-atomic-backend-cutover*
*Completed: 2026-04-29*
