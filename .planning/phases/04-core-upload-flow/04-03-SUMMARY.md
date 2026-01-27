---
phase: 04-core-upload-flow
plan: 03
subsystem: ui
tags: [react-dropzone, sonner, file-queue, drag-and-drop, hooks]

# Dependency graph
requires:
  - phase: 04-02
    provides: Upload types (FileQueueItem, LanguageCode, WhisperModel)
  - phase: 04-01
    provides: shadcn/ui components (Button, toast via sonner)
provides:
  - useFileQueue hook for queue state management
  - UploadDropzone component for drag-and-drop file uploads
affects: [04-04, 05-progress-tracking]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - useCallback for stable function references in hooks
    - noClick pattern for full-page drop targets

key-files:
  created:
    - frontend/src/hooks/useFileQueue.ts
    - frontend/src/components/upload/UploadDropzone.tsx
  modified: []

key-decisions:
  - "removeFile only removes pending files (per CONTEXT.md constraint)"
  - "Pre-fill selectedLanguage when detected, empty string otherwise"
  - "noClick: true with separate button for file dialog"

patterns-established:
  - "Hooks in frontend/src/hooks/ directory"
  - "Upload components in frontend/src/components/upload/ directory"
  - "useCallback for all hook functions to prevent re-renders"

# Metrics
duration: 3min
completed: 2026-01-27
---

# Phase 04 Plan 03: File Queue Hook and Upload Dropzone Summary

**useFileQueue hook with add/remove/update operations and UploadDropzone with full-page drag-and-drop using react-dropzone**

## Performance

- **Duration:** 3 min
- **Started:** 2026-01-27T14:45:02Z
- **Completed:** 2026-01-27T14:48:02Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- Created useFileQueue hook with queue state management (add, remove, clear, update)
- Created UploadDropzone component with full-page drop target pattern
- Auto-language detection integrated on file add
- Toast notifications for rejected files via sonner
- Drag overlay with backdrop blur and animated icon

## Task Commits

Each task was committed atomically:

1. **Task 1: Create useFileQueue hook** - `c65633d` (feat)
2. **Task 2: Create UploadDropzone component** - `e279adb` (feat)

## Files Created/Modified
- `frontend/src/hooks/useFileQueue.ts` - Queue state management hook with add/remove/update/clear operations
- `frontend/src/components/upload/UploadDropzone.tsx` - Full-page drop target with drag overlay and file picker button

## Decisions Made
- **removeFile respects pending-only constraint:** Per CONTEXT.md decision "Files can only be removed before processing starts"
- **Pre-fill selectedLanguage from detection:** When detectLanguageFromFilename returns a value, pre-fill both detectedLanguage and selectedLanguage; otherwise leave selectedLanguage empty to force user selection
- **noClick + explicit button pattern:** Used noClick: true on useDropzone to prevent entire page click opening file dialog, separate button calls open() explicitly
- **Both MIME wildcards and extensions:** Following RESEARCH.md Pitfall #1, accept config uses both audio/*/video/* wildcards AND explicit extensions for cross-platform reliability

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all imports resolved correctly, build passed on first attempt.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- useFileQueue hook ready for integration in upload page
- UploadDropzone ready to wrap page content
- Queue state can be wired to API upload endpoints in Phase 5
- FileQueueItem rendering (04-04) can now consume queue array

---
*Phase: 04-core-upload-flow*
*Completed: 2026-01-27*
