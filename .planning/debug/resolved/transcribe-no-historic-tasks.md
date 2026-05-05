---
status: resolved
trigger: "TranscribePage at http://127.0.0.1:5273/ui/ does NOT render historic tasks even though GET /task/all returns 461 items 200 OK"
created: 2026-04-29T00:00:00Z
updated: 2026-04-29T20:30:19Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "Strict Mode mount/unmount/remount race in useTaskHistory.ts causes the queue to never receive historic items. Mount #1 sets hasRunRef.current=true and starts the async fetch, then Strict Mode unmounts (cleanup sets cancelled=true). Mount #2 sees hasRunRef.current already true and bails. Mount #1's fetch resolves AFTER unmount, hits `if (cancelled) return;`, never calls addHistoricTasks. Net result: the entire path runs but the queue is never seeded."
  confirming_evidence:
    - "main.tsx:16 wraps app in <StrictMode>"
    - "useTaskHistory.ts:107-142 effect uses BOTH hasRunRef (persists across StrictMode mounts on same fiber) AND a per-mount `cancelled` closure variable (gated by cleanup at unmount)"
    - "Vitest test 'is idempotent across re-renders' uses rerender() not unmount/remount — doesn't simulate StrictMode mount cycle, hence 112 tests pass while runtime bug exists"
    - "Backend confirmed correct (461 items 200 OK), apiClient.get returns parsed JSON, fetchAllTasks correctly extracts data.tasks, seedQueueFromTasks logic is sound — bug is in the effect lifecycle, not data shape"
  falsification_test: "Removing <StrictMode> from main.tsx (or relaxing the hasRunRef guard) should make the queue render historic items. If the queue stays empty after that, hypothesis is wrong."
  fix_rationale: "The two guards (hasRunRef + cancelled) interact destructively. Correct fix: gate STATE-MUTATING side effects on `cancelled` only (per-mount), keep `hasRunRef` for fetch deduplication only, AND make the cleanup not pollute the next mount. Cleanest pattern: drop hasRunRef, rely on a module-level inflight promise (or simply accept the second mount and let dedupe in addHistoricTasks handle it — which it already does via taskId set). Choose the latter: it preserves SRP (no module-level cache), trusts existing dedupe (already covered by tests), and eliminates the race entirely."
  blind_spots: "Have not yet run live browser to confirm. Could also be: (a) /task/all returning 401 silently (apiClient redirects, but page is /ui/ not /login/, so we'd see redirect not empty queue), (b) ScrollArea collapsing rows visually, (c) some CSS overflow. But Strict Mode race fits ALL observed symptoms with no extra assumptions and 'used to work in tests' detail confirms behavior gap between rerender() and full remount."

next_action: Apply fix — remove hasRunRef guard, rely on existing taskId dedupe in addHistoricTasks. Add a regression test using StrictMode wrapper that catches the bug.

## Symptoms

expected: 461 historic tasks render in queue on page load
actual: Queue UI empty, no historic items visible
errors: none reported (no console errors mentioned)
reproduction: Visit http://127.0.0.1:5273/ui/ when logged in
started: unknown — new feature integration

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-04-29T00:00:00Z
  checked: backend /task/all
  found: returns 461 items, 200 OK (curl confirmed)
  implication: backend not at fault, bug is in frontend

- timestamp: 2026-04-29T00:00:00Z
  checked: 112 vitest tests for useTaskHistory + queue merge
  found: all pass
  implication: unit logic correct in isolation; bug is integration-level

- timestamp: 2026-04-29T00:00:00Z
  checked: main.tsx:16
  found: <StrictMode> wraps the app in development mode
  implication: every effect mounts/unmounts/remounts in dev — useTaskHistory must handle this

- timestamp: 2026-04-29T00:00:00Z
  checked: useTaskHistory.ts:105-142 effect lifecycle
  found: hasRunRef.current=true set on mount #1; cleanup sets cancelled=true on unmount; mount #2 reads hasRunRef.current still true and bails; mount #1 fetch resolves AFTER unmount, sees cancelled=true, returns without calling addHistoricTasks
  implication: StrictMode kills the seed entirely — both guards combine destructively

- timestamp: 2026-04-29T00:00:00Z
  checked: useTaskHistory.test.ts:209 (StrictMode-safe test)
  found: test uses rerender() not unmount/remount; renderHook does NOT wrap in StrictMode by default; bug never reproduces in vitest
  implication: regression test must explicitly use StrictMode wrapper

- timestamp: 2026-04-29T00:00:00Z
  checked: addHistoricTasks dedupe (useFileQueue.ts:51-61)
  found: taskId-based Set dedupe already prevents duplicate seeding on second call
  implication: hasRunRef guard is redundant — existing dedupe is sufficient and StrictMode-safe

## Resolution

root_cause: |
  Strict Mode interaction in useTaskHistory.ts: hasRunRef.current persists
  across the dev mount→unmount→remount cycle while `cancelled` is per-mount.
  Mount #1 schedules the async fetch, gets cancelled by the unmount, never
  seeds. Mount #2 sees hasRunRef already true and bails. Queue stays empty.
fix: |
  Removed hasRunRef. The async fetch is gated only by `cancelled` (per-mount).
  Dedupe is already handled at the queue layer by addHistoricTasks (taskId Set).
  StrictMode-safe regression test added that wraps the hook in <StrictMode>
  via renderHook's wrapper option.
verification: |
  - bunx tsc --noEmit → exit 0 (no type errors)
  - bun run vitest run → 19 files / 113 tests pass (was 112; +1 regression test)
  - useTaskHistory.test.ts → 15/15 pass (was 14/14; +1 StrictMode wrapper test)
  - Browser smoke verification still required from user (refresh /ui/ → 461 historic tasks visible)
files_changed:
  - frontend/src/hooks/useTaskHistory.ts
  - frontend/src/tests/hooks/useTaskHistory.test.ts
