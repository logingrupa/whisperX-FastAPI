# Phase 4: Core Upload Flow - Context

**Gathered:** 2026-01-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can upload audio/video files with language and model selection. This phase delivers the upload UI, file queue management, language detection from filename patterns, and model selection. Real-time progress tracking (Phase 5) and transcript viewing (Phase 6) are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Upload Zone Design
- Full-page drop target (entire page accepts file drops)
- Subtle overlay when dragging files over page (light tint, "Drop files here" text)
- Invalid files (non-audio/video) rejected with toast notification, don't appear in queue
- Always-visible "Select files" button for accessibility/discoverability

### Multi-file Queue Behavior
- Sequential processing (one file at a time)
- FIFO order (first in, first out), no reordering
- Individual remove button (X) on each queued file
- "Clear queue" button to remove all pending files
- Files can only be removed before processing starts

### Language Auto-Detection
- Inline badge next to filename shows detected language
- Separate dropdown always visible next to badge for override
- Language required before processing (force user selection if detection fails)
- Per-file language setting (no global default for batch)
- Tooltip on badge explains detection ("Detected from filename pattern")
- Core 3 languages (Latvian, Russian, English) pinned at top of dropdown
- Dropdown includes core 3 plus top 10-15 common languages (German, French, Spanish, etc.)

### Form Layout & Flow
- Settings configured after file selection (not before)
- Per-file model selection (each file can have different model)
- "Start all" button at bottom of queue
- Per-file start button for individual processing
- Default model: large-v3 (best quality)

### Claude's Discretion
- Queue item information density (balance filename, size, detected language, model, status)
- Badge format (abbreviation vs full language name based on space)
- Exact styling of overlay, buttons, badges
- Error state handling for edge cases

</decisions>

<specifics>
## Specific Ideas

- Detection pattern: A03=Latvian, A04=Russian, A05=English (from filename)
- User values accuracy over speed (large-v3 default confirms this)
- Both batch workflow ("Start all") and individual file control supported

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-core-upload-flow*
*Context gathered: 2026-01-27*
