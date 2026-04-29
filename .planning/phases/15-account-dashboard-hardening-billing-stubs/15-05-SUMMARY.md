---
phase: 15-account-dashboard-hardening-billing-stubs
plan: 05
subsystem: ui
tags: [auth, hydration, zustand, react, authstore, requireauth, msw, vitest]

requires:
  - phase: 15-01-groundwork
    provides: accountApi.fetchAccountSummary (suppress401Redirect inside) + AccountSummaryResponse + MSW account.handlers default-200 stub
  - phase: 15-03-account-me
    provides: backend GET /api/account/me 200 endpoint with anti-enumeration 401 parity
  - phase: 14-03-authstore
    provides: zustand authStore base shape + BroadcastChannel('auth') cross-tab sync + toAuthUser DRY mapper
provides:
  - authStore.refresh() — server-authoritative session hydration (Plan 14-03 user-null-on-reload gap closed)
  - authStore.isHydrating — boolean gate (initial true, flips false in finally) suppresses RequireAuth redirect-flash on boot
  - AuthUser interface gained trialStartedAt + tokenVersion (hydrated from /api/account/me)
  - RequireAuth — 3-state gate (hydrating null, unauth /login?next=, authed Outlet)
  - main.tsx boot probe — module-scope void useAuthStore.getState().refresh() before createRoot.render() (StrictMode-safe)
affects: [Plan 15-06 AccountPage]

tech-stack:
  added: []
  patterns:
    - "Try/finally hydration flag — guarantees isHydrating=false on every code path (success + 401 + ApiClientError + unexpected throw)"
    - "Module-scope boot probe (not useEffect) — avoids StrictMode double-hydration; single fire-and-forget refresh() call before render"
    - "3-state route gate via flat early returns (no nested-if) — hydrating short-circuit precedes user-null check"
    - "AuthUser extension via safe-default backfill — login/register populate trialStartedAt:null + tokenVersion:0; refresh() overrides with server payload"

key-files:
  created:
    - frontend/src/tests/routes/RequireAuth.test.tsx
  modified:
    - frontend/src/lib/stores/authStore.ts
    - frontend/src/routes/RequireAuth.tsx
    - frontend/src/main.tsx
    - frontend/src/tests/lib/stores/authStore.test.ts
    - frontend/src/tests/routes/AppRouter.test.tsx
    - frontend/src/tests/routes/KeysDashboardPage.test.tsx
    - frontend/src/tests/regression/smoke.test.tsx

key-decisions:
  - "[15-05]: refresh() error-class branch narrows on AuthRequiredError + ApiClientError (network 0/500/503/etc.) — silently leaves user null; truly unexpected errors re-thrown for visibility (T-15-04 mitigation, console-visible in dev)"
  - "[15-05]: Module-scope boot probe `void useAuthStore.getState().refresh()` in main.tsx (BEFORE createRoot.render) — StrictMode-safe single-fire (useEffect would double-hydrate); `void` operator makes fire-and-forget intent explicit"
  - "[15-05]: RequireAuth 3-state gate uses two separate flat guards (isHydrating then user===null) — fail-closed null render rather than risk leaking authed routes during in-flight probe; nested-if invariant 0 across all 5 modified files"
  - "[15-05]: toAuthUser populates trialStartedAt:null + tokenVersion:0 on login/register paths — Plan 14-03 endpoints don't return these fields; refresh() overrides with /api/account/me payload on next page load (DRY: zero new fetch sites — reuses fetchAccountSummary from Plan 15-01)"
  - "[15-05]: 3 sibling test files (AppRouter, KeysDashboardPage, smoke) updated to seed full AuthUser shape — Rule 3 deviation; TS strict mode would otherwise fail compile after AuthUser extension"
  - "[15-05]: AuthUser export hoisted (exported `type AuthUser` already public) — reused by AppRouter.test.tsx setUser() helper (drops adhoc inline shape, single source of truth)"

patterns-established:
  - "Hydration-flag try/finally: `try { ... set(user) } catch (err) { narrow + leave null } finally { set(isHydrating: false) }` — guarantees flag flip on every path; reusable for any future server-authoritative store"
  - "Module-scope side-effect probe: pre-render store calls in main.tsx (vs useEffect in App) for StrictMode-safe single-fire bootstrap"
  - "Test-state seed helper: `setState({ user, isHydrating: false })` in test beforeEach — bypasses boot probe; deterministic test starting condition"

requirements-completed: [UI-07]

duration: 9 min
completed: 2026-04-29
---

# Phase 15 Plan 05: Frontend Session Hydration — Summary

**authStore.refresh() + isHydrating + RequireAuth 3-state gate + main.tsx boot probe — closes Plan 14-03 user-null-on-reload gap; server is authoritative on every page load.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-04-29T22:27:00Z
- **Completed:** 2026-04-29T22:32:00Z
- **Tasks:** 2/2 (both TDD: RED + GREEN per task)
- **Files modified:** 7 (3 source + 4 test)
- **Files created:** 1 (RequireAuth.test.tsx)

## Accomplishments

- authStore extended with refresh() method, isHydrating flag, and AuthUser.{trialStartedAt, tokenVersion} — server-authoritative hydration via /api/account/me probe
- RequireAuth gate upgraded from 2-state (user|null) to 3-state (hydrating|unauth|authed) via two flat early-return guards — eliminates redirect-flash on boot reload
- main.tsx fires `void useAuthStore.getState().refresh()` once at module scope (pre-render) — StrictMode-safe single trigger, no double-hydration
- 17 new/updated TDD tests (14 authStore + 3 RequireAuth) green; full suite 70/70 passing across 11 files; tsc --noEmit clean
- Nested-if invariant 0 across all 5 modified TS/TSX files (DRY/SRP/tiger-style locked at file scope)

## Task Commits

TDD per task — RED first, then GREEN:

1. **Task 1 RED — failing authStore tests** — `ec7c8d7` (test)
2. **Task 1 GREEN — authStore.refresh + isHydrating + AuthUser fields** — `7a9a1b3` (feat)
3. **Task 2 RED — failing RequireAuth tests** — `ffbc3da` (test)
4. **Task 2 GREEN — RequireAuth gate + main.tsx boot probe** — `dbc3d11` (feat)

_Plan metadata commit follows this SUMMARY._

## Files Created/Modified

**Source (3 modified):**
- `frontend/src/lib/stores/authStore.ts` — added refresh(), isHydrating, AuthUser.{trialStartedAt, tokenVersion}; toAuthUser populates safe defaults; try/finally guarantees isHydrating flip on every code path
- `frontend/src/routes/RequireAuth.tsx` — added isHydrating selector + flat early-return guard before user-null check; render null while probe in flight
- `frontend/src/main.tsx` — added single `void useAuthStore.getState().refresh()` at module scope (after imports, before createRoot.render)

**Tests (1 created, 4 modified):**
- `frontend/src/tests/routes/RequireAuth.test.tsx` (created) — 3 tests covering hydrating-null / unauth-redirect / authed-Outlet transitions; MemoryRouter + Routes scaffolding
- `frontend/src/tests/lib/stores/authStore.test.ts` — added 6 refresh()/isHydrating tests (success/401/network-error/initial-state/login-defaults/logout-no-rehydrate); kept existing 8 tests; total 14 passing
- `frontend/src/tests/routes/AppRouter.test.tsx` — `setUser` helper now imports `AuthUser` type from authStore (DRY single source); seeds isHydrating:false in beforeEach
- `frontend/src/tests/routes/KeysDashboardPage.test.tsx` — seeded full AuthUser shape (trialStartedAt:null, tokenVersion:0) + isHydrating:false
- `frontend/src/tests/regression/smoke.test.tsx` — same seed update

## Verification Run

| Gate | Command | Result |
|------|---------|--------|
| TypeScript | `bunx tsc --noEmit` | exit 0 |
| authStore tests | `vitest run src/tests/lib/stores/authStore.test.ts` | 14/14 pass |
| RequireAuth tests | `vitest run src/tests/routes/RequireAuth.test.tsx` | 3/3 pass |
| Full suite (no regression) | `vitest run` | 70/70 pass across 11 files |
| Nested-if invariant | `grep -cE "^\s+if .*\bif\b" <5 files>` | 0/0/0/0/0 |
| main.tsx single refresh() | `grep -c "useAuthStore.getState().refresh()" main.tsx` | 1 |

## Acceptance Criteria

**Task 1 (authStore):** all 9 grep gates pass — `isHydrating: boolean`=1, `isHydrating: true`=1, `set({ isHydrating: false })`=1, `refresh: async`=1, `fetchAccountSummary`=3 (≥1), `trialStartedAt`=3 (≥2), `tokenVersion`=3 (≥2), nested-if=0, tsc=0, vitest=14 pass.

**Task 2 (RequireAuth + main.tsx):** all 8 gates pass — `isHydrating` in RequireAuth=5 (≥2), `if (isHydrating)`=1, `if (user === null)`=1, nested-if=0, `useAuthStore.getState().refresh()` in main=1, tsc=0, RequireAuth.test=3 pass, AppRouter.test still green=5 pass.

## Success Criteria — All Met

1. ✓ authStore.refresh() reads /api/account/me and populates user with id/email/planTier/trialStartedAt/tokenVersion
2. ✓ authStore.isHydrating starts true and flips false after refresh resolves OR rejects (finally block)
3. ✓ RequireAuth renders null while isHydrating=true (no redirect-flash on boot)
4. ✓ RequireAuth redirects to /login?next= after isHydrating=false + user=null
5. ✓ main.tsx fires refresh() exactly once at module load before App renders
6. ✓ AuthUser interface gains trialStartedAt + tokenVersion; existing login/register populate safe defaults

## Threat Mitigations Verified

| Threat ID | Surface | Mitigation Applied |
|-----------|---------|--------------------|
| T-15-04 | refresh() throws on unexpected error not silently | Catch narrows to AuthRequiredError + ApiClientError; truly unexpected errors propagate; isHydrating still flips via finally — verified by `refresh() flips isHydrating to false on network error` test |
| (boot-flash) | RequireAuth redirect-then-rerender race | isHydrating:true initial state + null render until flip — verified by `renders nothing while isHydrating=true (no redirect-flash)` test |
| T-15-09 | Cross-tab refresh race during hydration | Accepted (idempotent /me reads); BroadcastChannel logout still wired (existing UI-12 test green) |
| T-15-10 | plan_tier null/undefined crashes | accountApi.AccountSummaryResponse Pydantic-required server side; TypeScript narrows to string union; UI fallback in 15-06 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] Sibling test files broke compile after AuthUser extension**
- **Found during:** Task 1 (after authStore.ts AuthUser extension)
- **Issue:** `useAuthStore.setState({ user: { id, email, planTier } })` calls in 3 unrelated test files (AppRouter.test.tsx, KeysDashboardPage.test.tsx, smoke.test.tsx) failed strict-TS compile because new AuthUser requires trialStartedAt + tokenVersion
- **Fix:** Updated all 3 to seed full AuthUser shape (added `trialStartedAt: null, tokenVersion: 0`) + `isHydrating: false`; AppRouter test additionally migrated `setUser` helper signature from inline `{id, email, planTier}` to imported `AuthUser` type (DRY single source)
- **Files modified:** frontend/src/tests/routes/AppRouter.test.tsx, frontend/src/tests/routes/KeysDashboardPage.test.tsx, frontend/src/tests/regression/smoke.test.tsx
- **Commit:** 7a9a1b3 (folded into Task 1 GREEN — same compile-block boundary)

No Rule 1/2/4 issues. No auth gates encountered.

## Self-Check: PASSED

- ✓ frontend/src/lib/stores/authStore.ts — exists, modified, contains `refresh: async`, `isHydrating: true`, `fetchAccountSummary`
- ✓ frontend/src/routes/RequireAuth.tsx — exists, modified, contains `isHydrating` selector + early return
- ✓ frontend/src/main.tsx — exists, modified, contains 1 `useAuthStore.getState().refresh()` at module scope
- ✓ frontend/src/tests/routes/RequireAuth.test.tsx — created, contains 3 describe-blocks
- ✓ frontend/src/tests/lib/stores/authStore.test.ts — modified, contains `import { server }` + 6 new tests
- ✓ commits ec7c8d7, 7a9a1b3, ffbc3da, dbc3d11 — all present in `git log --oneline -6`
- ✓ tsc --noEmit exit 0
- ✓ vitest run: 70/70 passing across 11 files (no regression on Phase 14 + 15-01..04 tests)
