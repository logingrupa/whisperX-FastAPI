---
phase: 09-resilience-and-polish
plan: 02
subsystem: upload
tags: [cancel, retry-indicator, error-ux, tus, abort, progress-bar]

# Dependency graph
requires:
  - phase: 09-resilience-and-polish
    provides: Retry/resume infrastructure, classified error propagation, onRetrying callback
provides:
  - Cancel button during TUS upload (abort + DELETE + localStorage cleanup)
  - Retrying indicator replacing stale speed/ETA during retry delays
  - Full prop threading from orchestration through App -> FileQueueList -> FileQueueItem -> FileProgress
affects: [09-03 (final polish), 10 (deployment validation)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Abort ref map pattern: per-file abort function stored in useRef<Map>"
    - "Prop threading pattern: retryingFileId comparison at list level, boolean at item level"

key-files:
  created: []
  modified:
    - frontend/src/hooks/useUploadOrchestration.ts
    - frontend/src/components/upload/FileQueueItem.tsx
    - frontend/src/components/upload/FileProgress.tsx
    - frontend/src/components/upload/FileQueueList.tsx
    - frontend/src/App.tsx

key-decisions:
  - "Cancel resets to pending (not error) so user can re-upload without retry flow"
  - "Cancel button uses Square icon (stop symbol), not X (reserved for remove)"
  - "Cancel only visible during uploading stage, not during server-side processing"
  - "retryingFileId comparison done in FileQueueList, passed as boolean to FileQueueItem for SRP"

patterns-established:
  - "Abort ref map: Map<fileId, abortFn> for per-file cancel in sequential processing"
  - "State indicator override: isRetrying replaces speed/ETA row instead of adding new UI element"

# Metrics
duration: 4min
completed: 2026-02-05
---

# Phase 9 Plan 2: Cancel Button, Retry Indicator, and Error UX Wiring Summary

**Cancel button (Square icon) during TUS uploads, amber "Retrying..." indicator replacing stale speed/ETA, and full prop threading from orchestration to progress bar**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-05T19:13:47Z
- **Completed:** 2026-02-05T19:17:54Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Orchestration hook now tracks per-file abort functions via ref map and exposes handleCancel callback that sends DELETE to TUS server and resets file to pending
- FileProgress shows amber "Retrying..." text replacing stale speed/ETA metrics during retry delays, giving users confidence the system is recovering
- Cancel button (Square icon) appears during uploading stage and is hidden during server-side processing where cancel is not possible
- Full prop threading from useUploadOrchestration -> App -> FileQueueList -> FileQueueItem -> FileProgress

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire cancel, retrying state, and classified errors in orchestration** - `beeb139` (feat)
2. **Task 2: Add cancel button and retrying indicator to UI components** - `4a1fa10` (feat)

## Files Created/Modified

- `frontend/src/hooks/useUploadOrchestration.ts` - Added abort ref map, retryingFileId state, handleCancel callback, onRetrying wiring
- `frontend/src/components/upload/FileProgress.tsx` - Added isRetrying prop with amber "Retrying..." indicator
- `frontend/src/components/upload/FileQueueItem.tsx` - Added cancel button (Square icon) during uploading stage
- `frontend/src/components/upload/FileQueueList.tsx` - Threaded onCancel and retryingFileId props to queue items
- `frontend/src/App.tsx` - Destructured handleCancel and retryingFileId from orchestration, passed to FileQueueList

## Decisions Made

- **Cancel resets to pending:** User can re-upload immediately without going through retry/error flow
- **Square icon for cancel:** Distinct from X (remove) to avoid confusion -- standard stop/cancel icon
- **Cancel only during uploading stage:** Server-side processing has no cancel path, so button is hidden
- **retryingFileId comparison in list:** FileQueueList compares ID and passes boolean to item for SRP

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Threaded props through FileQueueList and App.tsx**
- **Found during:** Task 2
- **Issue:** Plan specified changes to FileQueueItem and FileProgress but not the parent components that pass props to them
- **Fix:** Added onCancel and retryingFileId to FileQueueList interface and wired in App.tsx
- **Files modified:** frontend/src/components/upload/FileQueueList.tsx, frontend/src/App.tsx
- **Verification:** TypeScript compiles without errors, props flow end-to-end
- **Committed in:** 4a1fa10 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Necessary for the props to actually reach the components. No scope creep.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RESIL-02 (cancel) fully wired from UI through to TUS abort
- RESIL-01 (retry indicator) visible in progress bar during retry delays
- RESIL-04 (classified errors) already showing via existing errorMessage/technicalDetail display
- Ready for 09-03 (final polish/verification)
- No blockers

---
*Phase: 09-resilience-and-polish*
*Completed: 2026-02-05*
