---
phase: 08-frontend-chunking
plan: 02
subsystem: ui
tags: [tus, hooks, upload-routing, file-size-threshold, taskId-handoff]

# Dependency graph
requires:
  - phase: 08-frontend-chunking
    plan: 01
    provides: TUS upload wrapper, speed tracker, constants
provides:
  - useTusUpload hook wrapping TUS library with speed/ETA tracking
  - File size routing in useUploadOrchestration (>= 80MB -> TUS, < 80MB -> direct)
  - updateFileUploadMetrics method on useFileQueue
  - Extended FileQueueItem with uploadSpeed/uploadEta fields
affects: [08-03 progress UI display of speed/ETA]

# Tech tracking
tech-stack:
  added: []
  patterns: [file-size routing, pre-generated taskId metadata handoff, stateless utility hook]

key-files:
  created:
    - frontend/src/hooks/useTusUpload.ts
  modified:
    - frontend/src/types/upload.ts
    - frontend/src/hooks/useFileQueue.ts
    - frontend/src/hooks/useUploadOrchestration.ts

key-decisions:
  - "File size routing at >= 80MB threshold with isTusSupported() fallback"
  - "processViaTus as separate function alongside existing processFile direct path"
  - "updateFileUploadMetrics in useFileQueue (Option A - SRP) rather than orchestration-local state"

patterns-established:
  - "Size-based upload routing transparent to all callers"
  - "Pre-generated taskId passed through TUS metadata callbacks"

# Metrics
duration: 2min
completed: 2026-01-29
---

# Phase 8 Plan 02: TUS Hook and Upload Routing Summary

**useTusUpload hook with file size routing: >= 80MB via TUS chunked upload, < 80MB via existing direct upload, with pre-generated taskId metadata handoff**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-29T20:24:57Z
- **Completed:** 2026-01-29T20:26:50Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Extended FileQueueItem with uploadSpeed/uploadEta optional fields for UI display
- Created stateless useTusUpload hook wrapping createTusUpload with UploadSpeedTracker integration
- Added updateFileUploadMetrics method to useFileQueue for SRP-compliant speed/ETA updates
- Added processViaTus function with pre-generated taskId and TUS metadata
- Added SIZE_THRESHOLD routing check in processFile -- transparent to all callers

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend upload types and create useTusUpload hook** - `d415c74` (feat)
2. **Task 2: Add file size routing to useUploadOrchestration** - `725df60` (feat)

## Files Created/Modified
- `frontend/src/types/upload.ts` - Added uploadSpeed/uploadEta optional fields to FileQueueItem
- `frontend/src/hooks/useTusUpload.ts` - Stateless hook returning startTusUpload with speed/ETA tracking
- `frontend/src/hooks/useFileQueue.ts` - Added updateFileUploadMetrics method
- `frontend/src/hooks/useUploadOrchestration.ts` - Added processViaTus + SIZE_THRESHOLD routing in processFile

## Decisions Made
- File size routing uses >= 80MB threshold with isTusSupported() browser capability check as fallback
- processViaTus is a separate useCallback alongside existing direct upload code (no modification to existing path)
- updateFileUploadMetrics lives in useFileQueue (SRP: queue owns its item data) rather than orchestration-local refs

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness
- useTusUpload hook ready for Plan 03 to display speed/ETA in progress UI
- uploadSpeed and uploadEta fields on FileQueueItem available for progress components
- Both upload paths (TUS and direct) flow through processFile -- existing handleStartFile/handleStartAll/handleRetry unchanged
- TypeScript and production build both pass cleanly

---
*Phase: 08-frontend-chunking*
*Completed: 2026-01-29*
