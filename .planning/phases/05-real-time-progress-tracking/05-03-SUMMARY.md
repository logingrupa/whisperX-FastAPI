---
phase: 05
plan: 03
subsystem: frontend/components
tags: [progress-ui, stage-badge, connection-status, file-queue]
dependency-graph:
  requires: ["05-01", "05-02"]
  provides: ["StageBadge", "FileProgress", "ConnectionStatus", "updated FileQueueItem"]
  affects: ["05-04"]
tech-stack:
  added: []
  patterns: ["status-based rendering", "conditional icons", "color-coded badges"]
key-files:
  created:
    - frontend/src/components/upload/StageBadge.tsx
    - frontend/src/components/upload/FileProgress.tsx
    - frontend/src/components/upload/ConnectionStatus.tsx
  modified:
    - frontend/src/components/upload/FileQueueItem.tsx
decisions:
  - id: "step-counter-visibility"
    choice: "Show step counter only for processing stages (not upload, complete, or error)"
    rationale: "Upload and complete are terminal states, step counter only meaningful during processing"
  - id: "connection-escalation"
    choice: "Subtle indicator for first 5 attempts, escalated warning after max attempts"
    rationale: "Per CONTEXT.md - avoid alarming users during brief disconnections"
  - id: "status-icons"
    choice: "CheckCircle2 for complete, AlertCircle for error (not progress bar)"
    rationale: "Per CONTEXT.md - completed files show checkmark, not 100% progress bar"
metrics:
  duration: "3 min"
  completed: "2026-01-28"
---

# Phase 05 Plan 03: Progress UI Components Summary

**One-liner:** Stage badges, progress bars, and connection status indicators integrated into file queue

## What Was Built

### Task 1: StageBadge Component
Created `frontend/src/components/upload/StageBadge.tsx`:

- Color-coded badge showing current processing stage
- Step counter in badge (e.g., "Transcribing (2/5)")
- Tooltip showing all stages via `getStageTooltip()`
- Color mapping from `STAGE_COLORS` in progressStages.ts
- Handles special "error" stage with red styling

### Task 2: FileProgress Component
Created `frontend/src/components/upload/FileProgress.tsx`:

- Horizontal progress bar using shadcn/ui Progress component
- Percentage text right-aligned (e.g., "45%")
- Optional spinner icon (Loader2 from lucide-react)
- CSS-animated transitions via Progress component

### Task 3: ConnectionStatus Component
Created `frontend/src/components/upload/ConnectionStatus.tsx`:

- Hidden when connected (returns null)
- Subtle "Reconnecting... (attempt X/5)" during reconnection
- Escalated amber warning after 5 failed attempts
- Manual "Reconnect" button when max attempts reached

### Task 4: Updated FileQueueItem
Modified `frontend/src/components/upload/FileQueueItem.tsx`:

**Status-based rendering:**
| Status | Displays |
|--------|----------|
| pending | Language/model selects, detected badge, start button, remove button |
| uploading/processing | StageBadge, FileProgress bar with spinner |
| complete | CheckCircle2 icon, green border, "Complete" badge |
| error | AlertCircle icon, red border, retry button, "Show details" link |

**New props added:**
- `onRetry?: (id: string) => void`
- `onShowErrorDetails?: (errorMessage: string, technicalDetail?: string) => void`

## Files Changed

| File | Change | Lines |
|------|--------|-------|
| frontend/src/components/upload/StageBadge.tsx | Created | +57 |
| frontend/src/components/upload/FileProgress.tsx | Created | +38 |
| frontend/src/components/upload/ConnectionStatus.tsx | Created | +61 |
| frontend/src/components/upload/FileQueueItem.tsx | Updated | +120 |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Step counter visibility | Processing stages only | Upload/complete are terminal, counter only meaningful during processing |
| Connection escalation | 5 attempts before warning | Avoid alarming users during brief disconnections |
| Complete state icon | CheckCircle2, not 100% bar | Per CONTEXT.md requirement |

## Deviations from Plan

None - plan executed exactly as written.

## Commit History

| Commit | Description |
|--------|-------------|
| 3501941 | feat(05-03): create StageBadge and FileProgress components |
| 95f44d1 | feat(05-03): create ConnectionStatus indicator component |
| 106d0f4 | feat(05-03): integrate progress display into FileQueueItem |

## Verification

- [x] `bun run build` passes without errors
- [x] All new components export correctly
- [x] FileQueueItem renders different states (pending, processing, complete, error)
- [x] StageBadge shows correct colors per stage
- [x] User approved components after manual review

## Next Phase Readiness

**For 05-04 (if exists) or Phase 6:**
- All progress UI components ready
- FileQueueItem shows real-time progress when hooked to WebSocket
- ConnectionStatus ready to display in page header
- Queue functions from 05-02 ready to wire up with upload API
