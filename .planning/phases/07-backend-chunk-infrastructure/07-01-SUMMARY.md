---
phase: 07-backend-chunk-infrastructure
plan: 01
subsystem: api
tags: [tus, chunked-upload, cors, fastapi, tuspyserver, resumable-upload]

# Dependency graph
requires:
  - phase: none
    provides: first plan in v1.1 milestone
provides:
  - TUS protocol router at /uploads/files/
  - CORS middleware exposing TUS headers
  - TUS upload directory creation on startup
  - tuspyserver dependency installed
affects:
  - 07-02 (upload-complete hook wiring)
  - 07-03 (cleanup scheduler for TUS_UPLOAD_DIR)
  - 08-frontend-chunk-integration (browser TUS client needs CORS headers)

# Tech tracking
tech-stack:
  added: [tuspyserver==4.2.3, apscheduler==3.10.4]
  patterns: [TUS protocol for resumable uploads, CORS expose_headers for protocol headers]

key-files:
  created: [app/api/tus_upload_api.py]
  modified: [app/main.py, pyproject.toml]

key-decisions:
  - "TUS files stored in UPLOAD_DIR/tus/ subdirectory (separate from streaming uploads)"
  - "CORS middleware added with wildcard origins for development (to be tightened in production)"
  - "Patched tuspyserver lock.py for Windows compatibility (fcntl -> msvcrt)"

patterns-established:
  - "TUS router wrapper pattern: create_tus_router() wrapped in APIRouter with prefix"
  - "TUS headers list defined as module-level constant for CORS configuration"

# Metrics
duration: 5min
completed: 2026-01-29
---

# Phase 7 Plan 01: TUS Router and CORS Summary

**TUS protocol router at /uploads/files/ using tuspyserver with CORS header exposure for chunked uploads**

## Performance

- **Duration:** 5 min
- **Started:** 2026-01-29T18:11:19Z
- **Completed:** 2026-01-29T18:16:23Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- TUS protocol endpoint live at /uploads/files/ accepting POST (create), PATCH (chunk), HEAD (resume)
- CORS middleware exposes all 8 TUS-specific headers for browser clients
- TUS upload directory auto-created on application startup
- tuspyserver and apscheduler added to project dependencies

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies and create TUS router module** - `408f323` (feat)
2. **Task 2: Mount TUS router in main.py and configure CORS for TUS headers** - `5c1008f` (feat)

## Files Created/Modified
- `app/api/tus_upload_api.py` - TUS protocol router with tuspyserver, exports tus_upload_router and TUS_UPLOAD_DIR
- `app/main.py` - CORS middleware with TUS headers, TUS router mount, TUS_UPLOAD_DIR startup creation
- `pyproject.toml` - Added tuspyserver==4.2.3 and apscheduler==3.10.4 dependencies

## Decisions Made
- TUS files stored in UPLOAD_DIR/tus/ subdirectory to keep TUS uploads separate from streaming uploads
- CORS uses wildcard origins for now (development); production hardening is a future concern
- days_to_keep=1 set as built-in backup expiry; Plan 03 will add scheduler-based cleanup

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Patched tuspyserver lock.py for Windows cross-platform compatibility**
- **Found during:** Task 1 (import verification)
- **Issue:** tuspyserver 4.2.3 uses `fcntl` module which is Unix-only; import fails on Windows with `ModuleNotFoundError: No module named 'fcntl'`
- **Fix:** Patched installed library's lock.py to conditionally use `msvcrt` on Windows and `fcntl` on Unix
- **Files modified:** .venv/Lib/site-packages/tuspyserver/lock.py (vendored patch, not committed)
- **Verification:** Import succeeds, server starts, TUS operations work
- **Note:** This is a development-only workaround. Production runs on Linux where fcntl is available natively.

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for development on Windows. No scope creep. Production unaffected.

## Issues Encountered
None beyond the fcntl deviation documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- TUS endpoint is live and accepting uploads at /uploads/files/
- Plan 02 can wire the upload-complete dependency hook
- Plan 03 can implement cleanup scheduler targeting TUS_UPLOAD_DIR
- Frontend (Phase 08) can begin TUS client integration with CORS headers in place

---
*Phase: 07-backend-chunk-infrastructure*
*Completed: 2026-01-29*
