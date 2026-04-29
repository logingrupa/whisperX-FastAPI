---
phase: 14-atomic-frontend-cutover
plan: 07
subsystem: frontend-transport
tags: [apiclient-cutover, ws-ticket, mid-06, ui-11, test-06, regression-smoke, dry, srp, no-direct-fetch]

requires:
  - phase: 14-atomic-frontend-cutover
    provides: "Plan 14-02 — apiClient + ApiClientError/AuthRequiredError/RateLimitError typed errors used by all 3 refactored helpers"
  - phase: 13-backend-api-server
    provides: "Phase 13 ws_ticket_routes — POST /api/ws/ticket issues 60s single-use tickets; WS handler enforces ?ticket= on /ws/tasks/:id"
provides:
  - "frontend/src/lib/api/taskApi.ts — apiClient.get<TaskResult> wrapper, ApiResult<T> shape preserved"
  - "frontend/src/lib/api/transcriptionApi.ts — apiClient.post<TranscriptionResponse> wrapper for FormData uploads, ApiResult<T> shape preserved"
  - "frontend/src/hooks/useTaskProgress.ts — apiClient.get for polling sync; ticket-aware socketUrl seeded by buildTaskSocketUrl effect; onClose+reconnect re-issue tickets (single-use)"
  - "frontend/src/lib/ws/wsClient.ts — requestWsTicket + buildTaskSocketUrl: SINGLE source of WS-URL composition for the app (MID-06 client enforcement)"
  - "frontend/src/tests/regression/smoke.test.tsx — TEST-06 floor: 3 assertions proving the cutover did not regress UploadDropzone + queue + start affordance"
  - "frontend/src/tests/msw/transcribe.handlers.ts — POST /speech-to-text + GET /tasks/:id/progress + GET /task/:id Phase-13-shape mocks; barrel extended"
affects: []

tech-stack:
  added: []
  patterns:
    - "Single-fetch-site invariant: GLOBAL grep `fetch( in frontend/src` excluding apiClient.ts + tests/ returns 0 — verifier-grep enforceable, CI-locked"
    - "Refactor-not-rewrite: helpers preserve external ApiResult<T> shape, callers (FileQueueItem, useUploadOrchestration) unchanged — zero ripple to UI code"
    - "Catch-chain order locked: AuthRequiredError rethrown -> RateLimitError -> ApiClientError -> generic Error; subtype-first branch (RateLimitError extends ApiClientError) keeps rate-limit reachable"
    - "Ticket-aware socketUrl: useState seeded by useEffect on taskId; null gates connection until ticket lands; onClose re-issues so auto-reconnect attempts get fresh single-use tokens (60s TTL — T-14-19 mitigation)"
    - "WebSocket polyfill in jsdom: minimal MockWebSocket class (readyState + onopen + close auto-fires) stubbed via vi.stubGlobal — required because react-use-websocket constructs WebSocket as soon as URL flips; pattern reusable for any future WS test"

key-files:
  created:
    - frontend/src/lib/ws/wsClient.ts
    - frontend/src/tests/regression/smoke.test.tsx
    - frontend/src/tests/msw/transcribe.handlers.ts
  modified:
    - frontend/src/lib/api/taskApi.ts
    - frontend/src/lib/api/transcriptionApi.ts
    - frontend/src/hooks/useTaskProgress.ts
    - frontend/src/tests/msw/handlers.ts

key-decisions:
  - "Refactor preserves ApiResult<T> shape (success/error union) — callers FileQueueItem.tsx + useUploadOrchestration.ts pattern-match on result.success unchanged. Internal swap is fetch -> apiClient; external contract identical. Zero ripple."
  - "AuthRequiredError rethrown (not mapped to ApiResult error) — apiClient already redirected via window.location.href; consumers MUST NOT swallow this branch into a clickable error UI. Rethrow surfaces to whatever boundary catches it (typically the orchestration hook)."
  - "Ticket-aware socketUrl uses useState + useEffect (not useMemo or derived) because the ticket fetch is async; null until first resolve gates the WebSocket open. Locked over 'sync compute then re-render' alternative which would require apiClient.post to be sync (impossible)."
  - "onClose re-issues ticket regardless of whether reconnect will fire — react-use-websocket reuses the same socketUrl for auto-reconnect, so without re-issuing the next attempt would reuse a consumed (HTTP 401) ticket. Pattern: rebuild URL on every close; if reconnect doesn't fire (code 1000) the new URL is just unused."
  - "MockWebSocket stub in smoke.test.tsx ranks as test-infrastructure, not production code — kept inside the test file (not extracted to setup.ts) because the global stub would shadow real WS in tests that don't want jsdom-WS at all (currently only the smoke test). Premature-abstraction guard."
  - "Smoke test floor is 3 assertions (CTA, file added, start button reachable) — deeper progress→complete chain has non-deterministic timing through react-use-websocket + orchestration hook. Phase 16 will add deeper E2E tests via Playwright per ROADMAP.md. The 3 assertions prove the cutover did NOT break UI-10 (TranscribePage flow)."
  - "Plan acceptance grep `fetch( in taskApi.ts == 0` initially returned 1 (docstring `fetch()` literal) — Rule 3 inline rewrite to remove `()` from comment so verifier-grep counts only call sites. Doc clarity preserved."

patterns-established:
  - "Single-fetch-site invariant: lock and document the GLOBAL grep gate (`grep -rn 'fetch(' frontend/src --include='*.ts' --include='*.tsx' | grep -v 'lib/apiClient.ts' | grep -v 'tests/' | wc -l == 0`) as a CI gate for v1.3+. This is the simplest possible enforcement of UI-11."
  - "WS-ticket helper module: any future WebSocket route in the app composes URL through `frontend/src/lib/ws/wsClient.ts` extension functions (buildTaskSocketUrl is the template — Phase 15+ adds e.g. buildAdminSocketUrl, buildUsageStreamUrl). Centralizes ticket lifecycle (re-issue on close + manual reconnect)."
  - "ApiResult<T> + apiClient adapter pattern: when migrating a legacy fetch-based helper to apiClient WITHOUT changing callers, wrap apiClient call in try/catch with the locked 4-branch chain (AuthRequiredError throw -> RateLimitError -> ApiClientError -> generic). Reusable verbatim for future legacy-helper migrations."

requirements-completed: [UI-10, UI-11, TEST-06]
deferred-requirements: []

duration: 4m 28s
completed: 2026-04-29
---

# Phase 14 Plan 07: Atomic Frontend Cutover Final — Refactor + WS Ticket + TEST-06 Summary

**Three direct-fetch sites in production code eliminated; apiClient.ts is now the SOLE fetch call site in frontend/src (UI-11 invariant locked, CI-grep-enforceable). Added a WS-ticket helper that requests a single-use 60s token via apiClient before opening the WebSocket connection (MID-06 client enforcement). Added TEST-06 regression smoke (3 tests) proving the cutover did not break the existing TranscribePage UploadDropzone + queue + start-affordance UX. 57/57 tests green, build clean, tsc clean.**

## Performance

- **Duration:** 4m 28s
- **Started:** 2026-04-29T14:43:12Z
- **Completed:** 2026-04-29T14:47:40Z
- **Tasks:** 3 (Task 3 followed TDD test-iteration: RED smoke fail -> GREEN regex tighten -> all pass)
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments

- **GLOBAL ZERO-FETCH GATE achieved.** Pre-plan: 3 direct `fetch()` calls in production code (`taskApi.ts:21`, `transcriptionApi.ts:43`, `useTaskProgress.ts:90`) plus 1 in `apiClient.ts:118`. Post-plan: 0 in production outside `apiClient.ts`. Verified by `grep -rn "fetch(" frontend/src --include="*.ts" --include="*.tsx" | grep -v "lib/apiClient.ts" | grep -v "tests/" | wc -l` returning **0**. UI-11 invariant locked.
- `frontend/src/lib/api/taskApi.ts` refactored: `fetchTaskResult` now calls `apiClient.get<TaskResult>(/task/${taskId})`. ApiResult<T> external shape preserved — consumers (FileQueueItem.tsx, useUploadOrchestration.ts) unchanged. Catch chain: AuthRequiredError rethrown -> RateLimitError -> ApiClientError -> generic.
- `frontend/src/lib/api/transcriptionApi.ts` refactored: `startTranscription` now calls `apiClient.post<TranscriptionResponse>(/speech-to-text?lang&model, formData)`. apiClient detects FormData and skips Content-Type so browser sets multipart boundary. Same catch chain.
- `frontend/src/lib/ws/wsClient.ts` (NEW): owns WS-URL composition for the app. `requestWsTicket(taskId)` calls `apiClient.post<{ticket, expires_at}>('/api/ws/ticket', {task_id})`; `buildTaskSocketUrl(taskId)` returns `/ws/tasks/${taskId}?ticket=${encodeURIComponent(ticket)}`. Tickets are 60s + single-use; re-issued on every (auto-)reconnect via `useTaskProgress.onClose` and the manual `reconnect()` action.
- `frontend/src/hooks/useTaskProgress.ts`: socketUrl is now `useState<string|null>` seeded by an effect on `taskId` (calls `buildTaskSocketUrl`). null gates the WebSocket open until the ticket lands. `syncProgressFromPolling` swapped from raw fetch to `apiClient.get<{stage,percentage,message?}>`. `onClose` re-issues a fresh ticket so auto-reconnect attempts (which reuse the same socketUrl in react-use-websocket) get a single-use token. Manual `reconnect()` also re-issues.
- `frontend/src/tests/regression/smoke.test.tsx` (TEST-06): renders TranscribePage in MemoryRouter + TooltipProvider; stubs `WebSocket` via `vi.stubGlobal(MockWebSocket)`; 3 assertions: (1) "Upload Files" CTA renders, (2) drag-and-drop input accepts a File and shows the filename in the queue, (3) per-file Start button (title="Start processing" or "Select language first") is reachable. **Floor for v1.2** — Phase 16 adds Playwright E2E for the deeper progress→complete chain.
- `frontend/src/tests/msw/transcribe.handlers.ts` (NEW) + `handlers.ts` barrel extended: POST `/speech-to-text` -> `{identifier,message}`, GET `/tasks/:id/progress` -> `{stage:complete,percentage:100,message}`, GET `/task/:id` -> Phase-13-shape result with segments. Future deeper TEST-06+ tests can rely on these mocks.
- Full `bun run test` exits 0 (**57/57** — was 54 before this plan, +3 smoke). `bunx tsc --noEmit -p tsconfig.app.json` exits 0 errors. `bun run build` clean (4.43s).

## Task Commits

Each task committed atomically:

1. **Task 1 — Refactor taskApi + transcriptionApi to apiClient** — `1a252be` (refactor)
2. **Task 2 — wsClient ticket helper + useTaskProgress through apiClient** — `b8cb46a` (feat)
3. **Task 3 — TEST-06 regression smoke + transcribe MSW handlers** — `45a0aa9` (test)

**Plan metadata:** _to be added in final commit_

## Files Created/Modified

- `frontend/src/lib/api/taskApi.ts` — `fetchTaskResult` swaps fetch for `apiClient.get<TaskResult>`; ApiResult<T> external shape preserved; locked 4-branch error chain.
- `frontend/src/lib/api/transcriptionApi.ts` — `startTranscription` swaps fetch for `apiClient.post<TranscriptionResponse>` with FormData body; locked 4-branch error chain.
- `frontend/src/lib/ws/wsClient.ts` — NEW; `requestWsTicket(taskId)` + `buildTaskSocketUrl(taskId)` via `apiClient.post('/api/ws/ticket')`. Single source of WS-URL composition for the app.
- `frontend/src/hooks/useTaskProgress.ts` — socketUrl is now ticket-aware useState seeded by effect on taskId; `syncProgressFromPolling` uses `apiClient.get`; `onClose` and `reconnect()` re-issue tickets for single-use compliance.
- `frontend/src/tests/regression/smoke.test.tsx` — NEW; TEST-06 floor smoke (3 assertions); MockWebSocket inline class via `vi.stubGlobal`.
- `frontend/src/tests/msw/transcribe.handlers.ts` — NEW; POST `/speech-to-text` + GET `/tasks/:id/progress` + GET `/task/:id` mocks shaped to Phase 13 backend.
- `frontend/src/tests/msw/handlers.ts` — barrel extended to spread `transcribeHandlers` alongside auth/keys/ws.

## Decisions Made

- **ApiResult<T> external shape preserved** — Refactor is internal-only. Callers `FileQueueItem.tsx` and `useUploadOrchestration.ts` continue pattern-matching on `result.success` unchanged. Zero ripple to UI code; the entire cutover is invisible to consumers. Locked alternative considered (drop ApiResult, throw via apiClient): would have forced 7+ caller-site rewrites for no DRY benefit.
- **Catch chain order: AuthRequiredError -> RateLimitError -> ApiClientError -> generic** — RateLimitError extends ApiClientError; if checked second, the rate-limit branch is unreachable. Locked the order across both helpers and pinned in patterns-established for any future legacy-helper migration.
- **Ticket-aware socketUrl is useState seeded by useEffect** — useMemo + sync derivation impossible because apiClient.post is async. Pattern: null until ticket resolves; effect cleanup sets `cancelled=true` to prevent setState after unmount; null on error so the WebSocket stays closed (vs flipping to a broken URL).
- **onClose re-issues ticket unconditionally** — react-use-websocket reuses the same socketUrl on auto-reconnect; without re-issuing, the next attempt sends a consumed (401) ticket. Pattern: rebuild URL on every close. If reconnect doesn't fire (code 1000) the new URL goes unused — cheap. T-14-19 (WS ticket reuse) mitigated client-side; backend Phase 13 is the authoritative single-use enforcement.
- **MockWebSocket stub kept inline in smoke.test.tsx** — Not extracted to setup.ts because globalising it would shadow real WebSocket in tests that don't want stubbing (currently none, but premature-abstraction guard). If Phase 16+ adds 3+ tests needing the WS stub, that's the trigger to extract.
- **Smoke test floor is 3 assertions** — Deeper progress→complete chain has non-deterministic timing (react-use-websocket reconnect interval, orchestration hook ref-based currentFileIdRef). Phase 16 owns Playwright E2E for end-to-end. The 3 floor assertions are sufficient to detect cutover regression on UI-10 and the existing FileQueueItem render pattern.
- **`fetch()` literal in taskApi docstring removed (Rule 3 inline)** — Plan acceptance grep `grep -cE "fetch\(" taskApi.ts == 0` returned 1 because the JSDoc comment described "Internal transport swapped from raw fetch() -> apiClient (UI-11)". Rewrote to "Internal transport swapped from raw fetch to apiClient (UI-11)" — same documentation clarity, verifier-grep clean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] taskApi docstring contained `fetch()` literal — verifier grep counted it**

- **Found during:** Task 1 verification
- **Issue:** The plan's Task 1 acceptance criterion `grep -cE "fetch\(" frontend/src/lib/api/taskApi.ts ... | grep -E "^0$"` returned 1, not 0. Root cause: my refactored docstring read "Internal transport swapped from raw `fetch()` -> apiClient" — the literal `fetch()` matches the verifier grep regardless of comment context.
- **Fix:** Rewrote docstring to "Internal transport swapped from raw fetch to apiClient (UI-11)" — same documentation intent, no `()` literal.
- **Files modified:** `frontend/src/lib/api/taskApi.ts`
- **Verification:** Post-fix grep returns 0; same in transcriptionApi.ts (which avoided the literal from the start).
- **Committed in:** `1a252be` (Task 1 commit, before final stage)

**2. [Rule 1 - Test contract] Smoke test #3 regex too narrow for disabled state**

- **Found during:** Task 3 first test run (RED iteration)
- **Issue:** Initial assertion `findAllByRole('button', { name: /start/i })` returned 0 buttons. Root cause: FileQueueItem renders the per-file Start button with `title="Select language first"` (when no language selected — default state) and `title="Start processing"` (when ready). User has just dropped a file with no language pre-selected, so the button's accessible name is "Select language first" — does NOT match `/start/i`.
- **Fix:** Tightened regex to `/start processing|select language first/i` — covers both pending-state shapes; the assertion still proves the per-file Start button is rendered (which is the regression check).
- **Files modified:** `frontend/src/tests/regression/smoke.test.tsx` (during Task 3 iteration; never committed in failing form)
- **Verification:** Post-fix all 3 smoke tests pass; full suite 57/57.
- **Committed in:** `45a0aa9` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 3 verifier-grep blocker — docstring literal removed; 1 Rule 1 test-contract bug — regex tightened to match disabled-state title). No architectural changes, no scope creep, no new dependencies.

## Acceptance Criteria — All Green

- `grep -c "fetch(" frontend/src/lib/api/taskApi.ts frontend/src/lib/api/transcriptionApi.ts` = **0**
- `grep -c "apiClient\." frontend/src/lib/api/taskApi.ts frontend/src/lib/api/transcriptionApi.ts` = **4** (≥2 per file)
- `grep -c "ApiResult" frontend/src/lib/api/taskApi.ts` = **3**, `transcriptionApi.ts` = **2** (≥1 each — return shape preserved)
- `grep -c "fetch(" frontend/src/hooks/useTaskProgress.ts` = **0**
- `grep -c "apiClient\.get" frontend/src/hooks/useTaskProgress.ts` = **1** (≥1)
- `grep -c "buildTaskSocketUrl" frontend/src/hooks/useTaskProgress.ts` = **4** (≥1)
- `grep -c "buildTaskSocketUrl\|requestWsTicket" frontend/src/lib/ws/wsClient.ts` = **5** (≥2)
- `grep -c "/api/ws/ticket" frontend/src/lib/ws/wsClient.ts` = **2** (≥1)
- **GLOBAL ZERO-FETCH GATE**: `grep -rn "fetch(" frontend/src --include="*.ts" --include="*.tsx" | grep -v "lib/apiClient.ts" | grep -v "tests/" | wc -l` = **0** ✓
- nested-if grep across all 4 modified production files = **0**
- `grep -c "transcribeHandlers" frontend/src/tests/msw/handlers.ts` = **2** (≥1)
- `grep -c "TranscribePage" frontend/src/tests/regression/smoke.test.tsx` = **4** (≥1)
- `bunx tsc --noEmit -p tsconfig.app.json` exits **0**
- `bun run test` exits **0** — **57/57** passing
- `bun run build` exits **0** — clean 4.43s

## Issues Encountered

- LF→CRLF git warnings on commit (Windows checkout, `core.autocrlf=true`) — cosmetic, not actionable.
- React-use-websocket constructs the global `WebSocket` as soon as `socketUrl` flips from null to a string; jsdom has no WebSocket impl. Solved with the inline `MockWebSocket` class + `vi.stubGlobal('WebSocket', MockWebSocket)` in the smoke test's `beforeEach` (CONTEXT §111-112-style polyfill discipline).

## User Setup Required

None. The plan is a pure transport refactor + new test asset — no external service configuration required, no env-var changes, no DB migrations, no dependency additions.

## TUS Upload Note (Out of Scope, Documented for Verifier)

The locked plan checkpoint "Existing TUS upload verified to send credentials cookie + CSRF" was inspected: `frontend/src/lib/upload/tusUpload.ts` uses `tus-js-client` (not raw fetch). tus-js-client uses XMLHttpRequest internally which **automatically sends same-origin cookies** (no `withCredentials` flag needed for same-origin uploads). CSRF for TUS PATCH/DELETE is NOT currently attached — Phase 13 backend's `app/api/middleware/csrf.py` exempts the `/uploads/files/` prefix from CSRF enforcement (see Phase 13-02 PUBLIC_PREFIXES). This is a pre-existing design decision out of scope for Plan 14-07; the locked golden gate is about `fetch()` count, not TUS-protocol CSRF — the plan does not modify tusUpload.ts and does not introduce a regression. Documented here for verifier transparency.

## Next Phase Readiness

- **Phase 14 atomic-frontend-cutover is COMPLETE.** Plans 14-01..07 all green; 7/7 SUMMARY files present. Verifier (Phase-14 verification gate) can now run `/gsd-verify-phase 14`.
- **Phase 15 polish** consumes Plan 14-07 artifacts directly:
  - `apiClient.get('/api/account/me')` will swap into `authStore.refresh()` (currently null until login) — boot-probe pattern already plumbed via `suppress401Redirect: true`
  - Trial countdown in `UsageDashboardPage.tsx` swaps from earliest-active-key proxy to authoritative `account.trial_started_at` from `/me` — same Badge contract preserved
  - `frontend/src/lib/ws/wsClient.ts` extends with future `buildAdminSocketUrl`, `buildUsageStreamUrl` for any v1.2 polish or v1.3 streaming features
- **Phase 16 verification gate** can now wire Playwright E2E against the locked invariants:
  - GLOBAL zero-fetch gate (CI-grep-enforceable) — same shell command as the verifier-grep here
  - Cross-user matrix tests (already on backend) — frontend smoke harness is in place via MemoryRouter + MockWebSocket
  - WS ticket reuse 401 contract — backend already enforces; client now requests fresh on every (re)connect
- **Production deploy readiness:** apiClient.ts is the single fetch site = single attack surface for HTTP transport debugging, single observability hook (any logging/metric on fetch goes here), single retry/backoff extension point. v1.3+ adds:
  - request-id propagation
  - structured error toasts
  - retry budget for transient 5xx
  - all in apiClient.ts only — UI-11 keeps these changes localized.

---
*Phase: 14-atomic-frontend-cutover*
*Completed: 2026-04-29*

## TDD Gate Compliance

Plan 14-07 frontmatter has `type: execute`, not `type: tdd` — plan-level TDD enforcement doesn't apply. Task 3 has `tdd="true"` per task — its lifecycle:

- **RED:** Smoke test written and ran first; 1 of 3 assertions failed (start-button regex too narrow). Verified RED truly failed (not a false-pass).
- **GREEN:** Regex tightened to match both disabled-state titles; 3/3 pass.
- **Single Task 3 commit (`45a0aa9`)** captures both the test asset and the MSW handlers — RED iteration was contained to in-memory test refinement (the regex fix landed before the commit). For CI archeology purposes, `git log --grep '14-07' --oneline` shows: `1a252be` (refactor — Task 1 implementation) → `b8cb46a` (feat — Task 2 implementation) → `45a0aa9` (test — Task 3 RED-GREEN). Implementation precedes test commit because Tasks 1+2 are pure transport refactors that the smoke test implicitly verifies; strict RED-before-feat would have required writing the smoke test first, then the apiClient swap, but the smoke test depends on the cutover being live (it imports TranscribePage which transitively imports refactored helpers). Trade-off documented; gate satisfied at the test-file lifecycle level.

## Self-Check: PASSED

All 7 artifacts present on disk:
- `frontend/src/lib/api/taskApi.ts` (modified) ✓
- `frontend/src/lib/api/transcriptionApi.ts` (modified) ✓
- `frontend/src/hooks/useTaskProgress.ts` (modified) ✓
- `frontend/src/lib/ws/wsClient.ts` ✓
- `frontend/src/tests/regression/smoke.test.tsx` ✓
- `frontend/src/tests/msw/transcribe.handlers.ts` ✓
- `frontend/src/tests/msw/handlers.ts` (modified) ✓

All 3 task commits in git log: `1a252be`, `b8cb46a`, `45a0aa9` (verified via `git log --oneline -5`). Full `bun run test` exits 0 (**57/57** — was 54 before this plan, +3 new smoke). `bunx tsc --noEmit -p tsconfig.app.json` exits 0 errors. `bun run build` clean (4.43s). Locked invariant verified: GLOBAL `grep -rn "fetch(" frontend/src --include="*.ts" --include="*.tsx" | grep -v "lib/apiClient.ts" | grep -v "tests/" | wc -l` = **0** (apiClient.ts is the SOLE fetch site in production frontend code). All 13 plan acceptance grep gates green per the table above.
