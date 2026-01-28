---
phase: 06-transcript-viewer-export
plan: 01
completed: 2026-01-28
duration: 3 min
subsystem: frontend-transcript
tags: [types, formatters, export, srt, vtt, json]

dependency_graph:
  requires: []
  provides:
    - TranscriptSegment type
    - TaskResult type
    - TaskMetadata type
    - SRT formatter
    - VTT formatter
    - TXT formatter
    - JSON formatter
    - useTranscriptDownload hook
  affects:
    - 06-02 (transcript viewer component)
    - 06-03 (export UI)

tech_stack:
  added: []
  patterns:
    - Pure formatter functions for testability
    - Blob URL creation with cleanup for memory safety
    - UTF-8 encoding for international characters

key_files:
  created:
    - frontend/src/types/transcript.ts
    - frontend/src/lib/formatters/srtFormatter.ts
    - frontend/src/lib/formatters/vttFormatter.ts
    - frontend/src/lib/formatters/txtFormatter.ts
    - frontend/src/lib/formatters/jsonFormatter.ts
    - frontend/src/lib/formatters/index.ts
    - frontend/src/hooks/useTranscriptDownload.ts
  modified: []

decisions:
  - decision: "SRT uses comma for ms, VTT uses period"
    reason: "Strict adherence to subtitle format specifications"
    scope: formatters
  - decision: "VTT voice tags for speakers instead of brackets"
    reason: "VTT spec recommends <v> tags for speaker identification"
    scope: vttFormatter
  - decision: "Blob URL revocation after download"
    reason: "Prevent memory leaks in browser"
    scope: useTranscriptDownload

metrics:
  tasks_completed: 3
  tasks_total: 3
  commits: 3
---

# Phase 06 Plan 01: Transcript Types and Format Utilities Summary

**One-liner:** Pure formatter functions for SRT/VTT/TXT/JSON export with UTF-8 blob download hook

## What Was Built

### 1. Transcript Types (`frontend/src/types/transcript.ts`)

Defined TypeScript interfaces matching backend schemas:

- **TranscriptSegment**: Core segment type with `start`, `end`, `text`, `speaker`
- **TaskMetadata**: Export metadata (filename, language, duration)
- **TaskResult**: Full task response matching `TaskResponse` from backend

### 2. Format Utilities (`frontend/src/lib/formatters/`)

Four pure formatter functions with spec-compliant output:

| Formatter | Output Format | Key Features |
|-----------|---------------|--------------|
| `formatTranscriptAsSrt` | SRT subtitle | Comma ms separator, `[SPEAKER]` prefix, sequential indices |
| `formatTranscriptAsVtt` | WebVTT | Period ms separator, `WEBVTT` header, `<v>` voice tags |
| `formatTranscriptAsTxt` | Plain text | Optional timestamps, speaker prefixes |
| `formatTranscriptAsJson` | JSON | 2-space indent, optional metadata |

### 3. Download Hook (`frontend/src/hooks/useTranscriptDownload.ts`)

React hook for browser file downloads:

- Creates UTF-8 encoded blobs for international character support
- Sets correct MIME types per format
- Revokes blob URLs to prevent memory leaks
- Exports `ExportFormat` type for consumers

## Technical Details

### SRT Format Example
```
1
00:00:01,500 --> 00:00:03,200
[SPEAKER_00] Hello world

2
00:00:03,500 --> 00:00:05,800
[SPEAKER_01] Hi there
```

### VTT Format Example
```
WEBVTT

00:00:01.500 --> 00:00:03.200
<v SPEAKER_00>Hello world</v>

00:00:03.500 --> 00:00:05.800
<v SPEAKER_01>Hi there</v>
```

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash | Message |
|------|---------|
| 2824049 | feat(06-01): create transcript types |
| a25b8de | feat(06-01): create transcript format utilities |
| fd4f380 | feat(06-01): create transcript download hook |

## Next Phase Readiness

**Ready for 06-02 (Transcript Viewer Component):**
- Types available for component props
- Formatters ready for download buttons
- Hook ready for export actions

**No blockers identified.**
