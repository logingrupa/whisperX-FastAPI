---
phase: 09-resilience-and-polish
plan: 01
subsystem: upload
tags: [tus, retry, exponential-backoff, resume, error-classification, tus-js-client]

# Dependency graph
requires:
  - phase: 08-frontend-chunking
    provides: TUS upload wrapper, hooks, and orchestration layer
provides:
  - Exponential backoff retry (1s/2s/4s) with smart error classification
  - localStorage-based upload resume via tus-js-client fingerprinting
  - Classified upload errors with user-friendly messages and technical detail
  - onRetrying callback for UI retry state signaling
affects: [09-02 (error UX), 10 (deployment validation)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "onShouldRetry callback pattern for selective retry based on HTTP status"
    - "Duck-typed error classifier (no runtime tus import needed)"
    - "Fire-and-forget async resume check preserving synchronous hook return"

key-files:
  created:
    - frontend/src/lib/upload/tusErrorClassifier.ts
  modified:
    - frontend/src/lib/upload/constants.ts
    - frontend/src/lib/upload/tusUpload.ts
    - frontend/src/hooks/useTusUpload.ts
    - frontend/src/hooks/useUploadOrchestration.ts

key-decisions:
  - "Exponential backoff [1000, 2000, 4000] -- 3 retries matching RESIL-01 spec"
  - "Permanent HTTP statuses (413, 415, 403, 410) never retried via onShouldRetry"
  - "Duck-typed TusDetailedErrorLike interface avoids runtime tus-js-client import in classifier"
  - "Fire-and-forget async IIFE for resume check preserves synchronous startTusUpload return"

patterns-established:
  - "Error classifier pattern: pure function mapping Error to {userMessage, technicalDetail, isRetryable}"
  - "onBeforeRetry forwarding: library -> hook -> orchestration for UI retry signals"

# Metrics
duration: 3min
completed: 2026-02-05
---

# Phase 9 Plan 1: TUS Retry, Resume, and Error Classification Summary

**Exponential backoff retry (1s/2s/4s) with smart HTTP status classification, localStorage resume via tus-js-client fingerprinting, and classified error propagation through hook layer**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-05T19:08:19Z
- **Completed:** 2026-02-05T19:11:32Z
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- TUS retry configured with exponential backoff (3 attempts at 1s, 2s, 4s) and smart retry logic that skips permanent errors (413, 415, 403, 410)
- Upload resume enabled via tus-js-client built-in fingerprint storage -- re-adding a file after page refresh resumes from stored offset
- Error classifier module maps HTTP statuses to user-friendly messages with technical detail for logging
- Hook-level onError signature updated to propagate classified fields (userMessage, technicalDetail, isRetryable) through to orchestration

## Task Commits

Each task was committed atomically:

1. **Task 1: Update TUS config and create error classifier** - `009771a` (feat)
2. **Task 2: Add resume flow and classified errors to useTusUpload hook** - `e04b0ac` (feat)

## Files Created/Modified

- `frontend/src/lib/upload/constants.ts` - Updated TUS_RETRY_DELAYS to [1000, 2000, 4000]
- `frontend/src/lib/upload/tusUpload.ts` - Enabled fingerprint storage, added onShouldRetry and onBeforeRetry
- `frontend/src/lib/upload/tusErrorClassifier.ts` - New error classifier with HTTP status mapping
- `frontend/src/hooks/useTusUpload.ts` - Added resume flow, classified error propagation, onRetrying callback
- `frontend/src/hooks/useUploadOrchestration.ts` - Migrated onError to accept classified error fields

## Decisions Made

- **Exponential backoff timing:** [1000, 2000, 4000] ms -- 3 retries matching RESIL-01 requirement
- **Permanent status set:** 413 (too large), 415 (unsupported type), 403 (forbidden), 410 (expired) -- never retried
- **Duck-typed classifier:** Used TusDetailedErrorLike interface instead of importing DetailedError at runtime, keeping the module pure
- **Async IIFE for resume:** Fire-and-forget pattern preserves the synchronous return signature of startTusUpload while enabling async findPreviousUploads

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RESIL-01 (retry), RESIL-03 (resume), and RESIL-04 (clear error messages) wired at hook level
- Ready for 09-02 (error UX polish) to consume classified error fields in UI components
- No blockers

---
*Phase: 09-resilience-and-polish*
*Completed: 2026-02-05*
