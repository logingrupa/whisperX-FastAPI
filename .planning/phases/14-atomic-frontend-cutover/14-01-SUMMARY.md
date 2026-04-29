---
phase: 14-atomic-frontend-cutover
plan: 01
subsystem: testing
tags: [vitest, jsdom, msw, react-testing-library, jest-dom, shadcn, zustand, react-hook-form, zod]

requires:
  - phase: 13-atomic-backend-cutover
    provides: "Auth v2 endpoints (cookie + bearer), CSRF middleware, locked CORS — frontend MSW mocks shape against these contracts"
provides:
  - "Vitest 3.2 + jsdom 25 + RTL 16 + user-event 14 + jest-dom 6 + MSW 2.13 test infra"
  - "Working `bun run test` runner (sentinel passes 2/2)"
  - "BroadcastChannel polyfill (multi-instance peer registry, vi.stubGlobal)"
  - "Writable window.location mock + navigator.clipboard mock"
  - "MSW Node server with split handlers (auth/keys/ws) and barrel re-export"
  - "MSW browser worker (public/mockServiceWorker.js) for runtime mocking"
  - "shadcn/ui new-york primitives: form (react-hook-form adapter), input, label, dialog, alert"
  - "Runtime deps: zustand 5, react-hook-form 7, zod 3, @hookform/resolvers 3"
  - "@radix-ui/react-{dialog,label} primitives for shadcn shells"
affects: [14-02, 14-03, 14-04, 14-05, 14-06, 14-07]

tech-stack:
  added:
    - vitest@^3.2.4
    - "@vitest/ui@^3.2.4"
    - jsdom@^25.0.1
    - msw@^2.13.0
    - "@testing-library/react@^16.1.0"
    - "@testing-library/user-event@^14.6.1"
    - "@testing-library/jest-dom@^6.6.3"
    - zustand@^5.0.2
    - react-hook-form@^7.54.2
    - zod@^3.24.1
    - "@hookform/resolvers@^3.10.0"
    - "@radix-ui/react-dialog@^1.1.4"
    - "@radix-ui/react-label@^2.1.1"
  patterns:
    - "MSW handlers split per resource (auth/keys/ws), barrel re-export from handlers.ts (DRY)"
    - "Vitest config separate from vite.config.ts (SRP — build vs test)"
    - "vi.stubGlobal for jsdom polyfills (BroadcastChannel) — test-only, never leaks to runtime"
    - "Writable window.location mock with afterEach reset — deterministic redirect assertions"
    - "shadcn primitive files written verbatim from new-york canonical (no customization — UI-13 bar)"

key-files:
  created:
    - frontend/vitest.config.ts
    - frontend/src/tests/setup.ts
    - frontend/src/tests/msw/handlers.ts
    - frontend/src/tests/msw/auth.handlers.ts
    - frontend/src/tests/msw/keys.handlers.ts
    - frontend/src/tests/msw/ws.handlers.ts
    - frontend/src/tests/__sentinel__.test.ts
    - frontend/public/mockServiceWorker.js
    - frontend/src/components/ui/form.tsx
    - frontend/src/components/ui/input.tsx
    - frontend/src/components/ui/label.tsx
    - frontend/src/components/ui/dialog.tsx
    - frontend/src/components/ui/alert.tsx
  modified:
    - frontend/package.json
    - frontend/bun.lock
    - frontend/.env.example

key-decisions:
  - "Vitest config in dedicated vitest.config.ts (not vite.config.ts test section) — SRP"
  - "BroadcastChannel polyfill uses peer-instance registry (Set per channel name) instead of single boundListener field — fixes broken plan code that would only deliver to last-added listener"
  - "MSW handlers split per resource (auth/keys/ws) re-exported from handlers.ts barrel — DRY/SRP"
  - "shadcn primitives written verbatim from new-york canonical source (no shadcn CLI invocation needed; CLI would have been interactive and unreliable in non-TTY)"
  - "msw.workerDirectory key in package.json pinned by `bunx msw init` — kept (canonical)"

patterns-established:
  - "Per-resource MSW handler files, single barrel — Plans 02-07 import from handlers.ts only"
  - "Sentinel-test pattern (__sentinel__.test.ts) — proves infra; future plans add real specs alongside"
  - "Test-only globals via vi.stubGlobal — runtime untouched"

requirements-completed: [TEST-01, TEST-02, TEST-03, TEST-05, UI-13]

duration: 3m 30s
completed: 2026-04-29
---

# Phase 14 Plan 01: Wave 1 Foundation Summary

**Vitest 3.2 + jsdom + RTL 16 + MSW 2.13 test runner online with sentinel passing; shadcn form/input/label/dialog/alert primitives + zustand/react-hook-form/zod runtime deps installed — Plans 02-07 unblocked.**

## Performance

- **Duration:** 3m 30s
- **Started:** 2026-04-29T13:16:04Z
- **Completed:** 2026-04-29T13:19:34Z
- **Tasks:** 2
- **Files modified:** 16 (13 created, 3 modified)

## Accomplishments

- Vitest jsdom test runner exits 0; sentinel proves jest-dom matchers + BroadcastChannel polyfill work end-to-end
- MSW Node server boots with handlers for /auth/*, /api/keys, /api/ws/ticket — wired into setup.ts beforeAll/afterAll
- MSW browser worker generated via `bunx msw init public/` (canonical, not hand-written)
- 5 shadcn new-york primitives (form/input/label/dialog/alert) added alongside existing badge/button/card/collapsible/progress/scroll-area/select/sonner/tooltip — no overwrites
- 13 deps locked in package.json across runtime + dev (bun install resolved 161 packages)

## Task Commits

1. **Task 1: Install runtime + dev deps and add shadcn UI components** — `b0de895` (chore)
2. **Task 2: Vitest config + tests/setup.ts + MSW scaffolding** — `dff607a` (chore)

**Plan metadata:** _to be added in final commit_

## Files Created/Modified

- `frontend/package.json` — added 7 runtime deps (zustand, react-hook-form, zod, @hookform/resolvers, @radix-ui/react-dialog, @radix-ui/react-label) + 7 dev deps (vitest, @vitest/ui, jsdom, msw, @testing-library/{react,user-event,jest-dom}); 3 new scripts (test, test:watch, test:ui); msw.workerDirectory pin
- `frontend/bun.lock` — locked 161 new resolved packages
- `frontend/vitest.config.ts` — jsdom env, globals, setupFiles, alias `@/*`, include `src/**/*.test.{ts,tsx}`
- `frontend/src/tests/setup.ts` — jest-dom matchers; MSW Node server (onUnhandledRequest:'error'); BroadcastChannel polyfill (peer-registry pattern, no nested-if); writable window.location; navigator.clipboard mock; per-test resets
- `frontend/src/tests/msw/auth.handlers.ts` — POST /auth/login (200 success + 401 wrong-password), POST /auth/register, POST /auth/logout
- `frontend/src/tests/msw/keys.handlers.ts` — GET /api/keys, POST /api/keys (returns plaintext once), DELETE /api/keys/:id
- `frontend/src/tests/msw/ws.handlers.ts` — POST /api/ws/ticket (mock-ticket-32chars)
- `frontend/src/tests/msw/handlers.ts` — barrel re-export combining 3 splits
- `frontend/src/tests/__sentinel__.test.ts` — 2 sanity tests (toHaveTextContent + BroadcastChannel.name)
- `frontend/public/mockServiceWorker.js` — canonical MSW worker (msw init output, do not edit)
- `frontend/src/components/ui/form.tsx` — react-hook-form adapter (`<Form>`, `<FormField>`, `<FormItem>`, `<FormLabel>`, `<FormControl>`, `<FormDescription>`, `<FormMessage>`); 15 FormField references
- `frontend/src/components/ui/input.tsx` — shadcn neutral input
- `frontend/src/components/ui/label.tsx` — Radix label primitive shell
- `frontend/src/components/ui/dialog.tsx` — Radix dialog (overlay, portal, content w/ close button, header/footer/title/description)
- `frontend/src/components/ui/alert.tsx` — cva variants (default + destructive); AlertTitle, AlertDescription
- `frontend/.env.example` — Phase 14 CORS/CSRF notes appended

## Decisions Made

- **Vitest config separated from vite.config.ts** — keeps build config minimal; test runner has its own resolve aliases. SRP.
- **BroadcastChannel polyfill rewritten** — plan code's `boundListener` single-field design would only deliver to the most recent listener; replaced with per-channel-name peer registry (`channelInstances: Map<string, Set<MockBroadcastChannel>>`). Each instance keeps its own listener set; postMessage iterates peers (excluding self) and fans out to all of their listeners. Correct cross-instance fan-out for cross-tab sync tests in Plan 03/05.
- **MSW handlers split per resource (auth/keys/ws)** — recommended by CONTEXT §144 (Claude's Discretion). Each resource lives in its own file; `handlers.ts` is a barrel. DRY in Plans 02/03/04 which import only `{ handlers }`.
- **shadcn primitives written verbatim** — `bunx shadcn` would prompt interactively; canonical new-york source written directly from upstream registry instead. Output identical, deterministic, no TTY dependency.
- **bunx msw init public/ --save** — generated `public/mockServiceWorker.js` and added `msw.workerDirectory` to package.json. Both kept (canonical msw practice).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] BroadcastChannel polyfill broadcast logic was broken**
- **Found during:** Task 2 (writing setup.ts)
- **Issue:** Plan-prescribed polyfill stored a single `boundListener` field per instance and overwrote it on every `addEventListener` call; postMessage compared against this stale reference. Result: only the most recently added listener on the same instance would skip self-delivery; multiple subscribers on different instances would not get cross-instance fan-out reliably.
- **Fix:** Replaced with peer-instance registry pattern. Each channel name maps to a `Set<MockBroadcastChannel>`; each instance owns a `listeners: Set<BcListener>`. `postMessage` iterates peers (excluding self) and dispatches to each peer's listeners. `close()` removes self from peer set and clears its listeners.
- **Files modified:** `frontend/src/tests/setup.ts`
- **Verification:** Sentinel test `BroadcastChannel polyfill installed` passes; structure satisfies grep guard `^\s+if .*\bif\b` returns 0 (no nested-if).
- **Committed in:** `dff607a` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix in plan code).
**Impact on plan:** No scope creep — fix is internal to setup.ts polyfill block, contract identical (`new BroadcastChannel(name)`, `postMessage`, `addEventListener('message', fn)`, `close()`). Plans 03/05/06 will work as written.

## Issues Encountered

- bun install warnings: LF→CRLF on commit (Windows checkout — `core.autocrlf=true`). Cosmetic only. No fix needed.
- `bunx shadcn add ...` skipped in favour of writing canonical files directly (see Decisions Made). Output identical, deterministic.

## User Setup Required

None — no external service configuration required. All dependencies installed via `bun install`; MSW worker generated automatically.

## Next Phase Readiness

- Plan 14-02 (apiClient) can now `import { setupServer }` from `msw/node` and assert against handlers.ts mocks.
- Plan 14-03 (authStore) can use `BroadcastChannel('auth')` knowing the polyfill delivers cross-instance.
- Plans 14-04/05/06 (LoginPage, RegisterPage, KeysDashboardPage) can render with shadcn `<Form>` + `<FormField>` + `<Input>` + `<Label>` + `<Dialog>` + `<Alert>` and assert via `@testing-library/jest-dom` matchers.
- `bun run test` is the canonical test command across the rest of Wave 1+2.

---
*Phase: 14-atomic-frontend-cutover*
*Completed: 2026-04-29*

## Self-Check: PASSED

All 13 artifacts + SUMMARY.md present on disk. Both task commits (`b0de895`, `dff607a`) present in git log. `bun run test` exits 0 (2/2 sentinel tests pass).
