---
phase: 06-transcript-viewer-export
plan: 03
completed: 2026-01-28
duration: 2 min
subsystem: frontend-transcript
tags: [components, transcript-viewer, download, shadcn-ui]

dependency_graph:
  requires:
    - 06-01 (types, formatters, download hook)
    - 06-02 (collapsible component)
  provides:
    - TranscriptSegmentRow component
    - TranscriptViewer component
    - DownloadButtons component
  affects: []

tech_stack:
  added: []
  patterns:
    - Timestamp formatting (MM:SS or HH:MM:SS)
    - Speaker label formatting (SPEAKER_00 to Speaker 1)
    - shadcn/ui ScrollArea for scrollable content

key_files:
  created:
    - frontend/src/components/transcript/TranscriptSegmentRow.tsx
    - frontend/src/components/transcript/TranscriptViewer.tsx
    - frontend/src/components/transcript/DownloadButtons.tsx
  modified: []

decisions:
  - decision: "Timestamps display MM:SS for short audio, HH:MM:SS for >1 hour"
    reason: "User-friendly format matching common media player conventions"
    scope: TranscriptSegmentRow
  - decision: "Speaker labels converted to friendly format (Speaker 1, 2, etc.)"
    reason: "SPEAKER_00 format from diarization not user-friendly"
    scope: TranscriptSegmentRow

metrics:
  tasks_completed: 3
  tasks_total: 3
  commits: 4
---

# Phase 06 Plan 03: Transcript Viewer UI Components Summary

**One-liner:** Three transcript display components - segment row, scrollable viewer, and multi-format download buttons

## What Was Built

### 1. TranscriptSegmentRow (`frontend/src/components/transcript/TranscriptSegmentRow.tsx`)

Single segment display component with:
- **Timestamp column**: Formats seconds as MM:SS (or HH:MM:SS for longer audio)
- **Speaker badge**: Converts SPEAKER_00 to "Speaker 1" for readability
- **Text content**: Full segment text with proper text wrapping
- Uses Badge component from shadcn/ui with outline variant

```typescript
<TranscriptSegmentRow segment={segment} />
// Renders: | 1:23 | [Speaker 1] | Hello world... |
```

### 2. TranscriptViewer (`frontend/src/components/transcript/TranscriptViewer.tsx`)

Scrollable transcript display with:
- **Header row**: Time, Speaker, Text column labels
- **ScrollArea**: shadcn/ui component for consistent scrollbar styling
- **Empty state**: "No transcript segments available" message
- **Configurable height**: Default 300px, adjustable via `maxHeight` prop

```typescript
<TranscriptViewer segments={segments} maxHeight="400px" />
```

### 3. DownloadButtons (`frontend/src/components/transcript/DownloadButtons.tsx`)

Export functionality with four format buttons:
- **SRT**: SubRip subtitle format
- **VTT**: WebVTT subtitle format
- **TXT**: Plain text with speakers
- **JSON**: Full export with metadata

Uses `useTranscriptDownload` hook from plan 06-01 for blob generation.

```typescript
<DownloadButtons segments={segments} filename="interview" metadata={taskMetadata} />
```

## Technical Details

### Timestamp Formatting
```typescript
formatTimestamp(3661) // "1:01:01" (1 hour, 1 minute, 1 second)
formatTimestamp(90)   // "1:30" (1 minute, 30 seconds)
```

### Speaker Label Formatting
```typescript
formatSpeakerLabel("SPEAKER_00") // "Speaker 1"
formatSpeakerLabel("SPEAKER_01") // "Speaker 2"
formatSpeakerLabel("John")       // "John" (pass through)
formatSpeakerLabel(null)         // null
```

### Component Layout
```
+--------+----------+--------------------------------+
| Time   | Speaker  | Text                           |
+--------+----------+--------------------------------+
| 0:00   | Speaker 1| First segment of speech...     |
| 0:15   | Speaker 2| Response from second speaker...|
| 0:28   | Speaker 1| Continuation of dialogue...    |
+--------+----------+--------------------------------+
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused index parameter from TranscriptSegmentRow**
- **Found during:** Final build verification
- **Issue:** TypeScript strict mode flagged unused `index` prop as error (TS6133)
- **Fix:** Removed `index` from props interface and component signature; index only used for key generation in parent
- **Files modified:** TranscriptSegmentRow.tsx, TranscriptViewer.tsx
- **Commit:** 9bf245b

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 13638c8 | feat | Create TranscriptSegmentRow component |
| 0f45970 | feat | Create TranscriptViewer component |
| d358db4 | feat | Create DownloadButtons component |
| 9bf245b | fix | Remove unused index prop from TranscriptSegmentRow |

## Verification Results

| Check | Status |
|-------|--------|
| TypeScript compiles (tsc --noEmit) | Pass |
| Build succeeds (bun run build) | Pass (3.85s) |
| All components importable | Pass |

## Integration Points

**Imports from 06-01:**
- `TranscriptSegment` type from `@/types/transcript`
- `TaskMetadata` type from `@/types/transcript`
- `useTranscriptDownload` hook from `@/hooks/useTranscriptDownload`

**Uses shadcn/ui components:**
- Badge (from `@/components/ui/badge`)
- Button (from `@/components/ui/button`)
- ScrollArea (from `@/components/ui/scroll-area`)

**Ready for integration:**
- Components can be used in FileQueueItem for completed transcriptions
- DownloadButtons can be placed next to TranscriptViewer for export

## Next Phase Readiness

**Phase 06 complete.** All transcript viewer and export functionality implemented:
- Types and formatters (06-01)
- Task API client and Collapsible component (06-02)
- Transcript viewer UI components (06-03)

**Integration ready:**
- Components can be composed with Collapsible for expandable transcript viewing
- Download buttons trigger immediate file download in user's preferred format
- All four export formats (SRT, VTT, TXT, JSON) fully functional
