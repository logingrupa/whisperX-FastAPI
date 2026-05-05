---
phase: quick-260505-l2w
reviewed: 2026-05-06T00:00:00Z
depth: quick
files_reviewed: 17
files_reviewed_list:
  - app/api/__init__.py
  - app/api/dependencies.py
  - app/api/schemas/usage_schemas.py
  - app/api/usage_routes.py
  - app/core/plan_tiers.py
  - app/main.py
  - app/services/free_tier_gate.py
  - app/services/usage_query_service.py
  - frontend/e2e/_fixtures/mocks.ts
  - frontend/e2e/usage-page/01-real-data.spec.ts
  - frontend/src/lib/api/usageApi.ts
  - frontend/src/routes/UsageDashboardPage.test.tsx
  - frontend/src/routes/UsageDashboardPage.tsx
  - frontend/src/tests/msw/handlers.ts
  - frontend/src/tests/msw/usage.handlers.ts
  - tests/integration/test_usage_routes.py
  - tests/unit/services/test_usage_query_service.py
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: issues_found
---

# Quick Task 260505-l2w: Code Review Report

**Reviewed:** 2026-05-06
**Depth:** quick
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Backend slice (plan_tiers extraction, UsageQueryService, /api/usage route, DI, OpenAPI) is clean. DRY/SRP/tiger-style largely honored: route is HTTP-only, service is business-only, repo SQL-only; magic numbers 5/30 confined to `app/core/plan_tiers.py`; subtype-first error catch chain present in frontend; refill-on-read invariant correctly implemented via `consume(tokens_needed=0)`.

Three real-but-non-blocking issues to address:

1. `TrialCountdownCard` uses `new Date()` directly — frontend tests + fixtures encode 2026 wall-clock dates that will silently flip behavior past their cutoffs (test stability erosion).
2. Integration test `test_get_usage_with_hour_bucket_returns_real_count` allows `(3, 4)` range to mask a real wall-clock-drift flake risk between fixture creation and service `now_utc`.
3. Frontend mount-effect duplicates the entire subtype-first error chain from `refresh()` — DRY violation.

Plus six info-level cleanups (unused import, unused re-exports, file-path drift, no `int(user.id)` boundary assertion, dead-code potential, fixture type vs. backend-produced range).

No security issues, no SQL injection vectors, no secrets, no missing-await, no auth bypass.

## Warnings

### WR-01: Frontend trial-expired branch reads real wall-clock; tests + fixtures hardcode 2026 dates

**File:** `frontend/src/routes/UsageDashboardPage.tsx:307`
**Issue:** `TrialCountdownCard` calls `const now = new Date();` and computes `daysLeftFrom(trialExpiresAtIso, now)`. The Vitest fixtures (`DEFAULT_USAGE_SUMMARY.trial_expires_at = '2026-05-08T12:00:00Z'`, `TRIAL_EXPIRED_USAGE.trial_expires_at = '2026-04-27T12:00:00Z'`) and the e2e fixture (`'2026-05-08T12:00:00Z'`) bake wall-clock dates into the mocks. Today's date controls which branch renders. The "happy-path trial" Vitest test (`test 1`) and e2e spec asserting `Trial` badge will flip into the `Trial expired ... Upgrade` branch once the calendar passes `2026-05-08`. The `TRIAL_EXPIRED_USAGE` test would have rendered the non-expired branch BEFORE 2026-04-27. Symmetric mirror of the backend's `now` injection is missing on the frontend.
**Fix:** Either (a) accept `now` as a prop into `TrialCountdownCard` defaulting to `new Date()` and let tests inject a stable instant; or (b) move expiry derivation server-side — return a precomputed `trial_expired: bool` and `trial_days_left: int` from `/api/usage` so the component renders pure data. Option (b) keeps the page tiger-style (no clock side-effects in render) and matches the backend's already-injected-now pattern in `UsageQueryService`. Bump the fixture dates to a far-future year (e.g. `2099-...`) as an interim if the schema change is out of scope.

```tsx
// Quick interim: accept now prop for testability.
function TrialCountdownCard({
  trialExpiresAtIso,
  onUpgrade,
  now = new Date(),
}: {
  trialExpiresAtIso: string;
  onUpgrade: () => void;
  now?: Date;
}) {
  const daysLeft = daysLeftFrom(trialExpiresAtIso, now);
  // ...
}
```

### WR-02: Integration test masks real clock-drift flake with `(3, 4)` allowance

**File:** `tests/integration/test_usage_routes.py:182`
**Issue:** `test_get_usage_with_hour_bucket_returns_real_count` seeds `last_refill=datetime.now(timezone.utc)` then asserts `body["hour_count"] in (3, 4)`. The comment admits "small clock-drift between last_refill and now_utc inside service may refill +1 token." This is the test working around its own fixture choice — if the bucket gets seeded close enough to a `int(elapsed * rate)` rollover boundary (rate = 5/3600 ≈ 0.0014; rollover at ~720s), the test would still flake. More importantly, the assertion can't catch a real off-by-one regression in `_count_used` because (3, 4) absorbs it.
**Fix:** Either (a) seed `last_refill` far in the past with a token count chosen so refill clamps at capacity (deterministic), or (b) inject `now` via a service-level test override / freezegun. The unit test in `test_usage_query_service.py:119` already proves the no-drift path correctly with `now=_NOW` and `last_refill=_NOW`; the integration test should pin `now` similarly rather than tolerate drift.

```python
# Pin the fixture instant well-before "now" with full-bucket math:
seed_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_seed_bucket(session_factory, bucket_key=..., tokens=2, last_refill=seed_time)
# Assert exact == 0 (refilled to capacity since seed was months ago)
# OR override service `now` parameter to match the seed.
```

### WR-03: Mount-effect duplicates the entire subtype-first error chain from `refresh()`

**File:** `frontend/src/routes/UsageDashboardPage.tsx:182-198`
**Issue:** `useEffect(() => { void fetchUsageSummary().then(...).catch(...) }, [])` reimplements the same RateLimit-then-ApiClient catch chain that `refresh()` already encapsulates 25 lines above. Two sources of truth for the same error policy violates CLAUDE.md DRY. If the `RateLimitError` retry-after copy or the generic alert string ever changes, both branches must be updated in lockstep.
**Fix:** Call `refresh()` from the mount effect.

```tsx
useEffect(() => {
  void refresh();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

(`refresh` is stable per render but not memoized; the eslint-disable is the standard one-shot-on-mount pattern. Alternatively wrap `refresh` in `useCallback` and add it to deps.)

## Info

### IN-01: Unused `MagicMock` import in service test module

**File:** `tests/unit/services/test_usage_query_service.py:20`
**Issue:** `from unittest.mock import MagicMock` — `MagicMock` is never referenced; tests use hand-rolled `_StubUserRepo` / `_StubRateLimitRepo` classes (the right call for SRP-clean stubs).
**Fix:** Delete the import line.

### IN-02: Integration test file landed at non-canonical path

**File:** `tests/integration/test_usage_routes.py`
**Issue:** PLAN.md repeatedly specifies `tests/integration/api/test_usage_routes.py` (e.g., PLAN.md:18, :469, :481, :490, :545, :569). File actually landed at `tests/integration/test_usage_routes.py`. Other Phase-19 route integration tests (`test_account_routes.py`, `test_billing_routes.py`, `test_key_routes.py`) all live at `tests/integration/`, so the existing layout is consistent with peers — but the plan directory `tests/integration/api/` was never created. Either the plan was wrong or the file should move. Pick one and lock the convention.
**Fix:** Either move the file to `tests/integration/api/test_usage_routes.py` (and migrate the peers) or update PLAN.md retroactively. Recommend leaving in place + amending plan since peers already cluster at `tests/integration/`.

### IN-03: Dead re-exports in `usageApi.ts`

**File:** `frontend/src/lib/api/usageApi.ts:48`
**Issue:** `export { ApiClientError, RateLimitError };` re-exports for "caller convenience (DRY with accountApi style)" but the only consumer (`UsageDashboardPage.tsx:56`) imports `ApiClientError, RateLimitError` directly from `@/lib/apiClient`. The re-export is unreferenced.
**Fix:** Either delete the re-export, or migrate the page to import from `@/lib/api/usageApi` so the wrapper is the single import surface (matches the doc comment's intent). Picking the second matches the UI-11 single-fetch-site invariant more cleanly.

### IN-04: Missing tiger-style boundary assertion on `int(user.id)` in route

**File:** `app/api/usage_routes.py:49`
**Issue:** `summary = usage_query_service.get_summary(int(user.id))` — `User.id: int | None` per the dataclass. `int(None)` raises `TypeError`. In practice `authenticated_user` resolves a persisted user (id always set), so this is safe today. Tiger-style says assert at boundaries — surface the invariant explicitly so a future regression in the auth chain doesn't fail with a confusing `TypeError`.
**Fix:**

```python
async def get_usage(
    user: User = Depends(authenticated_user),
    usage_query_service: UsageQueryService = Depends(get_usage_query_service),
) -> UsageSummaryResponse:
    """Return the caller's current usage summary."""
    assert user.id is not None, "authenticated_user must yield a persisted user"
    summary = usage_query_service.get_summary(user.id)
    return UsageSummaryResponse(**summary)
```

(Same pattern as `free_tier_gate.py:104` `user_id = int(user.id)  # type: ignore[arg-type]` — but the assert reads cleaner and gives a real failure message.)

### IN-05: `daily_minutes_used` is float-typed but always integer-valued; fixture lies

**File:** `frontend/src/tests/msw/usage.handlers.ts:32`
**Issue:** `daily_minutes_used: 4.5` and `7.5` (mocks.ts:137) — but the backend's `_count_used` returns `int(capacity - new_state["tokens"])` then wraps in `float(...)`. Capacity is integer minutes; refill returns int; subtraction is int. The wire value will ALWAYS be `N.0`, never `N.5`. Fixtures encode an impossible value. UX still works because `formatMinutes` runs `toFixed(1)`, but contract drift between fixture and reality means the test doesn't exercise what the backend actually emits.
**Fix:** Either (a) change fixtures to integer-valued floats (`4.0`, `7.0`); or (b) change the backend to return fractional minutes (track seconds, divide by 60.0). Option (a) is the no-cost match.

### IN-06: `_count_used` discards the `allowed` flag from `consume()` — flag this in a comment

**File:** `app/services/usage_query_service.py:117`
**Issue:** `new_state, _ = consume(...)`. `consume` always returns `allowed=True` when `tokens_needed=0` (per `core/rate_limit.py:48-51`), so discarding is correct. Worth a one-line comment so a future reader doesn't wonder why the flag is dropped — or assert `_ is True` as a tiger-style sanity check.
**Fix:**

```python
new_state, allowed = consume(
    {"tokens": bucket.tokens, "last_refill": bucket.last_refill},
    tokens_needed=0,
    now=now, rate=rate, capacity=capacity,
)
assert allowed, "tokens_needed=0 must always be allowed (refill-only call)"
return max(0, capacity - new_state["tokens"])
```

---

_Reviewed: 2026-05-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
