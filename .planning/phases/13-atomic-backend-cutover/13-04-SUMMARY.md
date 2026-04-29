---
phase: 13-atomic-backend-cutover
plan: 04
subsystem: backend-routes
tags: [api-keys, fastapi, show-once, soft-delete, trial-countdown, anti-enumeration, integration-tests]
requires:
  - phase: 13-01
    provides: AuthSettings.{V2_ENABLED, COOKIE_SECURE, COOKIE_DOMAIN, JWT_TTL_DAYS}; feature_flags
  - phase: 13-02
    provides: get_authenticated_user / get_key_service / get_auth_service dependencies; DualAuthMiddleware (consumed by integration tests)
  - phase: 13-03
    provides: auth_router (cookie-acquisition path for tests); _set_auth_cookies helpers; rate_limiter singleton
  - phase: 11
    provides: KeyService.create_key (show-once contract) / list_for_user / revoke_key; AuthService class; IUserRepository.update; ApiKey + User entities
provides:
  - app.api.key_routes.key_router with POST / GET / DELETE /api/keys (3 endpoints)
  - app.api.schemas.key_schemas.{CreateKeyRequest, CreateKeyResponse, ListKeyItem}
  - AuthService.start_trial_if_first_key — idempotent trial-countdown trigger (RATE-08)
  - tests/integration/test_key_routes.py — 12 integration tests
affects:
  - plan 13-09 (atomic flip): mounts key_router on FastAPI app under is_auth_v2_enabled() guard
  - phase 14 frontend: consumes POST /api/keys (show-once UX), GET /api/keys (dashboard list), DELETE (revoke button)
tech-stack:
  added: []
  patterns:
    - "Show-once plaintext: only CreateKeyResponse exposes `key`; ListKeyItem omits it (T-13-16)"
    - "Cross-user opaque 404: list_for_user(user.id) scopes to caller; foreign id returns same 404 as missing id (T-13-15 — no enumeration)"
    - "Trial-countdown idempotency: AuthService.start_trial_if_first_key fires only when key_count_after_create == 1 AND trial_started_at is None (three flat guards)"
    - "DRY auth resolution: every route uses Depends(get_authenticated_user) — never parses Authorization or session cookies directly"
    - "SRP routes: HTTP only; KeyService owns key creation/listing/revocation; AuthService owns user-state mutations"
    - "Slim FastAPI test app: per-test Container override + DualAuthMiddleware mount + tmp SQLite — full bearer + cookie integration coverage without main.py wiring"
key-files:
  created:
    - app/api/key_routes.py
    - app/api/schemas/key_schemas.py
    - tests/integration/test_key_routes.py
  modified:
    - app/services/auth/auth_service.py
key-decisions:
  - "Cross-user 404 mechanism via list-then-filter (`next((k for k in key_service.list_for_user(int(user.id)) if int(k.id) == key_id), None)`) — KeyService.list_for_user already scopes to user_id, so foreign keys never appear in the candidate list (no enumeration)"
  - "AuthService.start_trial_if_first_key takes key_count_after_create as caller-supplied integer (not derived inside the method) — keeps the service free of repository knowledge about ApiKey listings (SRP); route layer counts via key_service.list_for_user"
  - "Three flat guards in start_trial_if_first_key (key_count != 1 / user is None / trial_started_at is not None) — avoids nested-if; verifier-checked grep returns 0"
  - "Schema split: CreateKeyResponse has `key: str` (plaintext shown ONCE), ListKeyItem omits it — Pydantic serialization enforces show-once at the schema layer (defence-in-depth beyond business logic)"
  - "Integration tests use TWO TestClient instances against the same app to test cross-user — separate cookie jars simulate two real users; same DB so the cross-user DELETE actually reaches User A's row"
  - "Bearer integration test bootstraps via cookie path (register → POST /api/keys with cookie) then re-issues the plaintext as Authorization: Bearer for a 2nd-key POST — proves DualAuthMiddleware bearer leg + key_router auth check both work end-to-end"
patterns-established:
  - "Show-once UX: plaintext only in 201 POST response; never in GET list; never logged"
  - "Opaque cross-user 404: identical 404 + body for missing-id and foreign-id (no enumeration)"
  - "Trial-trigger pattern: route counts post-create state (list_for_user) and passes count to AuthService — SRP boundary kept clean"
requirements-completed:
  - KEY-01 (authenticated user can create named API keys via API)
  - KEY-04 (full API key shown exactly once at creation — `key` field only in CreateKeyResponse)
  - KEY-05 (user lists keys with id, name, prefix, created_at, last_used_at, status)
  - KEY-06 (multiple active keys allowed; verified by 5-key integration test)
  - KEY-07 (DELETE soft-deletes; revoked rows persist; status=revoked surfaced in list)
  - RATE-08 (7-day trial counter starts at first key creation; idempotent on subsequent creations)
duration: ~4 min
completed: 2026-04-29
---

# Phase 13 Plan 04: API Key Management Routes Summary

POST/GET/DELETE /api/keys endpoints with show-once plaintext (KEY-04) + opaque cross-user 404 (T-13-15) + trial-countdown trigger on first key creation (RATE-08), all behind 12 passing integration tests covering bearer + cookie auth paths.

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-29T10:21:14Z
- **Completed:** 2026-04-29T10:25:15Z
- **Tasks:** 3
- **Files created:** 3
- **Files modified:** 1

## Accomplishments

- 3 API key management endpoints exposed on `key_router` (mounted under `is_auth_v2_enabled()` guard in plan 13-09)
- Show-once UX: plaintext returned ONCE in 201 response (`key` field on `CreateKeyResponse` only); list endpoint serializes via `ListKeyItem` which lacks `key` entirely — defence-in-depth at the schema layer
- Soft-delete pattern: DELETE sets `revoked_at = now`; row persists for audit; GET still returns it with `status="revoked"` (KEY-07)
- Multiple active keys per user: verified end-to-end with 5-key creation integration test (KEY-06; no cap)
- Cross-user DELETE returns opaque 404 — identical body to missing-id 404 (T-13-15 anti-enumeration mitigation via list_for_user-then-filter)
- Trial-countdown trigger: `AuthService.start_trial_if_first_key(user_id, key_count_after_create)` fires only when post-create count is 1 AND `trial_started_at` is None — three flat guards, no nested-if, idempotent on subsequent creations
- 12 integration tests cover: show-once, DB-persistence-of-hash-only, trial-trigger first-key, trial-idempotent-second-key, multi-active, list-with-statuses, no-plaintext-in-list, soft-delete, cross-user-404, missing-id-404, 401-no-auth, bearer-auth-path

## Task Commits

Each task was committed atomically:

1. **Task 1: AuthService.start_trial_if_first_key + key_schemas** - `30cb055` (feat)
2. **Task 2: key_routes.py with POST/GET/DELETE** - `f4d7763` (feat)
3. **Task 3: Integration tests for key_routes** - `459cd25` (test)

## Files Created/Modified

### Created

- `app/api/schemas/key_schemas.py` (32 lines) — Pydantic v2 `CreateKeyRequest` (1-64 char name), `CreateKeyResponse` with show-once `key: str` field, `ListKeyItem` with no `key` field
- `app/api/key_routes.py` (87 lines) — `key_router = APIRouter(prefix="/api/keys", tags=["API Keys"])`; 3 endpoints all using `Depends(get_authenticated_user)` (DRT); `_to_list_item` helper extracted; cross-user 404 via list-then-filter
- `tests/integration/test_key_routes.py` (328 lines, 12 cases) — slim FastAPI app per test mounts auth_router + key_router + DualAuthMiddleware; per-test Container override against tmp SQLite; uses `select(ORMApiKey)` + `select(ORMUser)` for DB introspection (hash-not-plaintext, trial_started_at)

### Modified

- `app/services/auth/auth_service.py` — appended `start_trial_if_first_key(user_id, key_count_after_create) -> None` after `logout_all_devices`; three flat guards; calls `user_repository.update(user_id, {"trial_started_at": now})` exactly once per first-key event

## Verification

### Acceptance Grep Gates

| Gate | Expected | Actual |
| ---- | -------- | ------ |
| `def start_trial_if_first_key` in auth_service.py | 1 | 1 |
| nested-if (`^\s+if .*\bif\b`) in auth_service.py | 0 | 0 |
| `class CreateKeyResponse\|class ListKeyItem\|class CreateKeyRequest` in key_schemas.py | 3 | 3 |
| `key: str` in key_schemas.py (only in CreateKeyResponse — show-once) | 1 | 1 |
| `@key_router.post` in key_routes.py | 1 | 1 |
| `@key_router.get` in key_routes.py | 1 | 1 |
| `@key_router.delete` in key_routes.py | 1 | 1 |
| `Depends(get_authenticated_user)` in key_routes.py (DRT — every endpoint) | 3 | 3 |
| `key=plaintext` in key_routes.py (show-once) | 1 | 1 |
| `start_trial_if_first_key` in key_routes.py (RATE-08) | 1 | 1 |
| `404` in key_routes.py (cross-user opaque) | ≥1 | 4 |
| nested-if in key_routes.py | 0 | 0 |
| `@pytest.mark.integration` in test_key_routes.py | ≥10 | 12 |
| named test functions in test_key_routes.py | ≥10 | 10 (of named set) |

### Test Outcomes

```
$ pytest tests/integration/test_key_routes.py -v -m integration
12 passed in 2.07s
```

| # | Test | Status |
| - | ---- | ------ |
| 1 | test_create_key_returns_plaintext_once | PASS |
| 2 | test_create_key_persists_prefix_and_hash_only | PASS |
| 3 | test_create_key_starts_trial_on_first | PASS |
| 4 | test_create_key_idempotent_trial_on_second | PASS |
| 5 | test_create_key_multiple_active_allowed | PASS |
| 6 | test_get_keys_lists_all_with_status | PASS |
| 7 | test_get_keys_no_plaintext_in_list | PASS |
| 8 | test_delete_key_soft_deletes | PASS |
| 9 | test_delete_key_cross_user_returns_404 | PASS |
| 10 | test_delete_unknown_key_returns_404 | PASS |
| 11 | test_create_key_requires_auth | PASS |
| 12 | test_bearer_auth_can_create_key | PASS |

### Regression

```
$ pytest tests/unit/services/auth tests/unit/core tests/unit/api -q
142 passed in 0.71s
```

(Pre-existing collection failures in `tests/unit/domain` + `tests/unit/infrastructure` from missing `factory_boy` — out of scope, untouched.)

## Show-Once Evidence

```
$ grep -n "key: str" app/api/schemas/key_schemas.py
20:    key: str = Field(..., description="Plaintext API key (whsk_*) — shown ONCE")
```

The `key` field appears in exactly ONE schema (CreateKeyResponse). `ListKeyItem` has no plaintext field. Integration test `test_get_keys_no_plaintext_in_list` confirms `assert "key" not in items[0]` passes against the live FastAPI serialization layer.

## Trial-Countdown Verification

The trial trigger is wired in route layer:

```python
# app/api/key_routes.py — POST /api/keys
plaintext, api_key = key_service.create_key(int(user.id), body.name)
all_keys = key_service.list_for_user(int(user.id))
auth_service.start_trial_if_first_key(int(user.id), len(all_keys))
```

`start_trial_if_first_key` early-returns if `key_count_after_create != 1`, if user is None, or if `trial_started_at is not None` — making it idempotent across N concurrent and sequential POSTs (T-13-17 accept).

Integration tests `test_create_key_starts_trial_on_first` and `test_create_key_idempotent_trial_on_second` exercise both legs against a real SQLite DB — first POST sets `users.trial_started_at`, second POST does NOT reset it (compared timestamps must be equal).

## Cross-User 404 Mechanism

```python
# app/api/key_routes.py — DELETE /api/keys/{key_id}
owned = next((k for k in key_service.list_for_user(int(user.id)) if int(k.id) == key_id), None)
if owned is None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
```

`KeyService.list_for_user(user_id)` is the existing Phase 11 method that returns ONLY keys owned by `user_id`. Foreign keys never appear in the candidate list — the `next(...)` filter therefore returns `None` for both "key doesn't exist anywhere" AND "key belongs to another user", emitting an identical 404 body. T-13-15 (information disclosure via cross-user enumeration) mitigated.

Integration test `test_delete_key_cross_user_returns_404` registers User A, creates key K1 under A's cookie session, then registers User B (separate `TestClient` instance = separate cookie jar) and attempts `DELETE /api/keys/K1.id`. Asserts 404 + identical body to `test_delete_unknown_key_returns_404`. Also asserts User A's key remains active (cross-user attempt did NOT cause a side effect).

## Decisions Made

- **AuthService.start_trial_if_first_key takes count as parameter** — keeps the service free of ApiKey-repository knowledge (SRP). The route layer counts via `key_service.list_for_user(...)` and passes the count. Pure SRP — auth_service owns user-state mutations only.
- **Three flat guards** — `if key_count_after_create != 1`, `if user is None`, `if user.trial_started_at is not None`. Verifier-checked: zero nested-if. Each guard is a separate top-level statement.
- **Schema-layer show-once enforcement** — `ListKeyItem` lacks the `key` field entirely. Even if a buggy route handler tried to leak plaintext on a list response, Pydantic would discard it. Defence-in-depth on top of the route's explicit `key=plaintext` only in CreateKeyResponse.
- **Test isolation pattern reuse** — integration tests follow the 13-03 pattern: per-test Container, providers.Factory(sessionmaker(bind=tmp_engine)), limiter.reset() teardown. Adds DualAuthMiddleware mount to enable bearer auth integration test.
- **Two TestClient instances for cross-user test** — `TestClient(app)` twice creates two cookie jars against the same app+DB. Simulates two real users without process-isolation overhead.

## Deviations from Plan

None — plan executed exactly as written.

No architectural deviations, no auto-fixes triggered, no auth gates encountered. All grep gates and acceptance criteria hit on first attempt; all 12 integration tests passed first run.

## Issues Encountered

- Pre-existing collection errors in `tests/unit/domain` + `tests/unit/infrastructure` from missing `factory_boy` package — out of scope, untouched.

## Threat Mitigations Applied

| Threat ID | Mitigation |
| --------- | ---------- |
| T-13-15 (info disclosure — cross-user DELETE) | `key_service.list_for_user(user.id)` scopes to caller; non-owned id returns 404 (same as not-found); integration test verifies identical body across both legs and confirms User A's key remains active after User B's attempt |
| T-13-16 (info disclosure — plaintext leak via list) | `ListKeyItem` schema has no `key` field; Pydantic serializer drops any accidentally added value; integration test verifies `"key" not in list_items[0]` |
| T-13-17 (tampering — trial-trigger race) | accept (per plan); idempotent guard `if user.trial_started_at is not None: return` makes concurrent first-key POSTs converge — SQLite serializes; final state has a single trial_started_at timestamp |
| T-13-18 (repudiation — audit trail) | Phase 11 `KeyService` logs `id=, prefix=` on create; revoked rows persist (no hard-delete) — `test_delete_key_soft_deletes` confirms revoked row survives in list |

## User Setup Required

None — all changes are server-side. Routes will be mounted on `app/main.py` in plan 13-09 (atomic flip with `is_auth_v2_enabled()` guard).

## Next Phase Readiness

- `key_router` is built but **NOT yet mounted** on `app/main.py`. Plan 13-09 (atomic flip) will `app.include_router(key_router)` under the V2 feature flag, alongside auth_router (13-03), account_router (13-05), and billing_router (13-06).
- The DualAuthMiddleware → `request.state.user` → `Depends(get_authenticated_user)` contract from 13-02 is now consumed by 3 production routes (POST/GET/DELETE /api/keys); contract holds.
- Frontend (Phase 14) can now build dashboards against the locked POST/GET/DELETE /api/keys shape — show-once modal on POST, list-with-status table on GET, soft-delete-with-confirm on DELETE. Schema field names (`id`, `name`, `prefix`, `key` (POST only), `created_at`, `last_used_at`, `status`) are stable.

## Self-Check

Files created exist:
- `app/api/key_routes.py` → FOUND
- `app/api/schemas/key_schemas.py` → FOUND
- `tests/integration/test_key_routes.py` → FOUND

Files modified:
- `app/services/auth/auth_service.py` → MODIFIED (start_trial_if_first_key appended)

Commits exist:
- `30cb055` → FOUND (Task 1)
- `f4d7763` → FOUND (Task 2)
- `459cd25` → FOUND (Task 3)

## Self-Check: PASSED

---
*Phase: 13-atomic-backend-cutover*
*Completed: 2026-04-29*
