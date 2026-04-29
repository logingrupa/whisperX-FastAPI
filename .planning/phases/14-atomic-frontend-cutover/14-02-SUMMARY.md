---
phase: 14-atomic-frontend-cutover
plan: 02
subsystem: ui
tags: [apiclient, fetch, csrf, cookies, typed-errors, msw, vitest, tiger-style]

requires:
  - phase: 14-atomic-frontend-cutover
    provides: "MSW Node server + handlers barrel + writable window.location mock + jest-dom matchers (Plan 14-01) — apiClient tests assert against handlers.ts and mocked location"
  - phase: 13-atomic-backend-cutover
    provides: "401/429 response shapes + Retry-After header + csrf_token cookie contract — apiClient policy mirrors these"
provides:
  - "frontend/src/lib/cookies.ts — readCookie(name) document.cookie parser (DRY single source for csrf_token reads)"
  - "frontend/src/lib/apiErrors.ts — ApiClientError / AuthRequiredError / RateLimitError typed class hierarchy"
  - "frontend/src/lib/apiClient.ts — central HTTP wrapper (get/post/put/patch/delete) — single fetch site for all non-WS calls"
  - "Locked policy: credentials: 'include' default, X-CSRF-Token on POST/PUT/PATCH/DELETE, 401 -> /login?next=, 429 -> RateLimitError, 4xx/5xx -> ApiClientError"
  - "Module-load assertEnvSane() boot guard (tiger-style)"
affects: [14-03, 14-04, 14-05, 14-06, 14-07]

tech-stack:
  added: []
  patterns:
    - "Single fetch() site enforced — `grep -c 'fetch(' frontend/src/lib/apiClient.ts` == 1; Plans 03-07 import { apiClient } only"
    - "Typed error hierarchy — callers narrow via `instanceof RateLimitError` rather than parsing strings or status codes (tiger-style)"
    - "CSRF double-submit attached automatically on state-mutating methods (POST/PUT/PATCH/DELETE) — read from csrf_token cookie via readCookie helper"
    - "_redirectingTo401 module-level latch prevents redirect loops within same window lifetime (T-14-05 mitigation)"
    - "suppress401Redirect option escape hatch for authStore.refresh() boot probe — throws AuthRequiredError without navigating"

key-files:
  created:
    - frontend/src/lib/cookies.ts
    - frontend/src/lib/apiErrors.ts
    - frontend/src/lib/apiClient.ts
    - frontend/src/tests/lib/cookies.test.ts
    - frontend/src/tests/lib/apiClient.test.ts
  modified: []

key-decisions:
  - "patch method added alongside get/post/put/delete — success criteria called for it; cheap symmetry, future-proofs Plan 06 if any key-rename endpoint goes PATCH"
  - "buildBody treats null body identically to undefined — passing `null` from caller (e.g., apiClient.post(path, null) for empty-body POST) produces no body and no Content-Type, matching backend's empty-POST contract"
  - "parseErrorBody never throws — wraps response.json() in try/catch; falls back to `HTTP <status>` detail and raw=null when backend returns non-JSON (e.g., proxy 502 HTML page)"
  - "_redirectingTo401 latch is module-level (not per-request) — once tripped within a page lifetime, no further redirects fire even if multiple in-flight 401s land. Test isolation NOT a concern for this plan (only one redirect test); would need explicit reset hook if a future plan adds multi-redirect tests"
  - "AuthRequiredError still THROWN even when redirect fires — gives caller a chance to abort downstream chained promises before the page navigates away (avoids dangling .then() on the redirect path)"

patterns-established:
  - "Single source HTTP — Plans 03-07 MUST `import { apiClient } from '@/lib/apiClient'`; direct fetch() in non-test app code is grep-checkable to be 0 after Plan 07 refactor"
  - "Typed error narrowing — callers handle 429 via `if (err instanceof RateLimitError) renderInlineCountdown(err.retryAfterSeconds)`; no string parsing"
  - "Cookie read helper centralized — readCookie is the only document.cookie parser site (DRY); future cookies (e.g., theme preference) extend the same helper"

requirements-completed: [UI-08, UI-09, UI-11, TEST-04, TEST-05]

duration: 2m 28s
completed: 2026-04-29
---

# Phase 14 Plan 02: Central apiClient Wrapper Summary

**Single fetch() site for all non-WebSocket HTTP — typed error hierarchy (ApiClientError/AuthRequiredError/RateLimitError), automatic CSRF + credentials, locked 401-redirect / 429-RateLimitError policy, and tiger-style boot assertion. Plans 03-07 unblocked.**

## Performance

- **Duration:** 2m 28s
- **Started:** 2026-04-29T13:23:16Z
- **Completed:** 2026-04-29T13:25:44Z
- **Tasks:** 2
- **Files modified:** 5 (5 created, 0 modified)

## Accomplishments

- One central HTTP wrapper — `frontend/src/lib/apiClient.ts` is the SINGLE `fetch()` call site in the codebase (verified: `grep -c "fetch(" frontend/src/lib/apiClient.ts` == 1). Plans 03-07 import `{ apiClient }` and `{ RateLimitError }` from this module; Plan 07 will refactor `frontend/src/lib/api/{taskApi,transcriptionApi}.ts` and `frontend/src/hooks/useTaskProgress.ts` to drop direct fetches.
- Typed error hierarchy ready for tiger-style narrowing: `ApiClientError` (base), `AuthRequiredError` (401), `RateLimitError` (429 with `retryAfterSeconds`). Callers `instanceof`-check rather than string-match; `code` field carries backend-supplied error codes (`AUTH_REQUIRED`, `RATE_LIMITED`, `REGISTRATION_FAILED`, `NETWORK_ERROR`).
- Locked policy enforced and tested: `credentials: 'include'` on every request; `X-CSRF-Token` header attached on POST/PUT/PATCH/DELETE from `csrf_token` cookie via `readCookie`; 401 redirects to `/login?next=<encoded current path+search>`; 429 throws `RateLimitError` with parsed `Retry-After` (fallback 60s); other 4xx/5xx throw `ApiClientError` with backend `detail` + `code` + raw body; network failure throws `ApiClientError(0, ..., 'NETWORK_ERROR')`.
- Tiger-style boot assertion `assertEnvSane()` runs at module load — refuses to boot if `getApiBaseUrl()` returns a non-relative non-http value (e.g., a misconfigured `VITE_API_URL` typo). Current default of `''` (relative URLs, locked from CONTEXT §94) passes assertion silently.
- 16/16 tests pass across the suite (2 sentinel + 4 cookies + 10 apiClient).

## Task Commits

Each task was committed atomically:

1. **Task 1: Cookie reader + typed error classes** — `fe8bf00` (feat)
2. **Task 2: apiClient.ts (get/post/put/patch/delete) + 10 tests covering 401/429/CSRF/credentials** — `0c030a4` (feat)

**Plan metadata:** _to be added in final commit_

## Files Created/Modified

- `frontend/src/lib/cookies.ts` — `readCookie(name)` parses `document.cookie`; encodeURIComponent prefix match (does not match suffix collisions like `xcsrf_token`); decodeURIComponent on returned value
- `frontend/src/lib/apiErrors.ts` — `ApiClientError(status, message, code?, body?)` extends Error; `AuthRequiredError` extends ApiClientError(401, ..., 'AUTH_REQUIRED'); `RateLimitError(retryAfterSeconds, body?)` extends ApiClientError(429, ..., 'RATE_LIMITED')
- `frontend/src/lib/apiClient.ts` — `apiClient.get/post/put/patch/delete<T>()`; single internal `request<T>(opts)`; `buildHeaders` (Accept + Content-Type + CSRF on state-mutating); `buildBody` (FormData passthrough, null/undefined skip, JSON.stringify); `redirectTo401` (latch-guarded `/login?next=`); `parseRetryAfter` (60s fallback); `parseErrorBody` (try/catch JSON, fallback to status string); `assertEnvSane` runs at module load; re-exports error classes
- `frontend/src/tests/lib/cookies.test.ts` — 4 tests: missing cookie returns null, present cookie returns value, URL-decoded values, suffix-mismatch (xcsrf_token must not match csrf_token)
- `frontend/src/tests/lib/apiClient.test.ts` — 10 tests: GET 200 JSON parse, POST attaches X-CSRF-Token, GET does NOT attach X-CSRF-Token, 401 redirect with ?next= preservation, 401 with suppress401Redirect=true skips redirect, 429 RateLimitError with Retry-After=42, 429 fallback to 60s when header missing, 422 ApiClientError shape with detail+code, 204 returns undefined, credentials: 'include' default

## Decisions Made

- **`patch` method added alongside `get/post/put/delete`** — success criteria explicitly required `get/post/put/delete/patch methods`. Cheap symmetry; future Plan 06 (key rename) might use PATCH.
- **`buildBody` treats `null` identically to `undefined`** — Plan-prescribed test passes `null` to `apiClient.post(path, null, { suppress401Redirect: true })` for empty-body POST. Both produce no `body` and no `Content-Type`, matching the backend `/auth/refresh` contract (empty-body POST relying on cookie session).
- **`parseErrorBody` never throws** — wraps `response.json()` in try/catch; falls back to `{ detail: 'HTTP <status>', raw: null }` when backend returns non-JSON (proxy 502 HTML, network text errors). Caller code never sees a parser exception leak through.
- **`_redirectingTo401` latch is module-level** — once tripped during a page lifetime no further redirects fire (T-14-05 mitigation). Test isolation: only one redirect test (#4) in this plan; if future plans add multiple redirect tests, they'll need an explicit reset hook (resetRedirectLatch export) — left as YAGNI for now.
- **`AuthRequiredError` still THROWN even when redirect fires** — caller's downstream `.then(...)` chain MUST abort. Throwing gives Promise.reject path so chained code doesn't run between fire-redirect and actual navigation.

## Deviations from Plan

None — plan executed exactly as written. The two minor enhancements (adding `patch` method per success criteria, `null` body handling for the suppress401Redirect test) are codified in the plan-prescribed test file and success criteria, so they are not deviations.

## Issues Encountered

- LF→CRLF git warnings on commit (Windows checkout, `core.autocrlf=true`) — cosmetic only.

## User Setup Required

None — no external service configuration required. Module loads transparently in dev (relative URLs via Vite proxy), prod (relative same-origin URLs), and test (relative URLs against MSW Node server).

## Next Phase Readiness

- **Plan 14-03 (authStore)** can `import { apiClient } from '@/lib/apiClient'` and call `apiClient.post('/auth/login', creds)`; `apiClient.post('/auth/logout')`; `apiClient.get('/api/account/me')` for hydration; use `{ suppress401Redirect: true }` on the boot probe so unauthenticated boot doesn't loop-redirect.
- **Plan 14-04 (router/RequireAuth)** consumes authStore — no direct apiClient interaction expected.
- **Plan 14-05 (LoginPage/RegisterPage)** invokes authStore.login/register; surfaces `RateLimitError.retryAfterSeconds` as inline countdown alert (no toast spam); surfaces `ApiClientError.code === 'INVALID_CREDENTIALS'` / `'REGISTRATION_FAILED'` as generic non-enumerating error message.
- **Plan 14-06 (KeysDashboardPage/UsageDashboardPage)** uses `apiClient.get('/api/keys')`, `apiClient.post('/api/keys', {name})`, `apiClient.delete('/api/keys/:id')`; relies on backend 401 → automatic redirect (no manual auth checks needed in component).
- **Plan 14-07 (existing-helper refactor)** drops 3 direct fetch sites in `frontend/src/lib/api/{taskApi,transcriptionApi}.ts` + `frontend/src/hooks/useTaskProgress.ts` (verified count) — replaces with apiClient calls. After Plan 07, `grep -rn "fetch(" frontend/src --include="*.ts" --include="*.tsx" | grep -v "tests/"` should yield only `frontend/src/lib/apiClient.ts`.

---
*Phase: 14-atomic-frontend-cutover*
*Completed: 2026-04-29*

## Self-Check: PASSED

All 5 artifacts (cookies.ts, apiErrors.ts, apiClient.ts, cookies.test.ts, apiClient.test.ts) + SUMMARY.md present on disk. Both task commits (`fe8bf00`, `0c030a4`) present in git log. `bun run test` exits 0 (16/16 tests pass).
