# Phase 5: Real-Time Progress Tracking - Context

**Gathered:** 2026-01-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Users see live transcription progress with stage indicators and error handling via WebSocket. This phase covers the frontend progress display, WebSocket connection management, and error presentation. The backend WebSocket infrastructure was built in Phase 1.

</domain>

<decisions>
## Implementation Decisions

### Progress display
- Progress bar with percentage (horizontal bar, percentage text alongside)
- Smooth animation between percentage updates
- Progress inline with file row (not expanded or separate panel)
- No ETA/time estimate
- Spinner icon alongside progress bar during active processing
- Only active file shows progress bar; queued files show "Queued" status
- Completed files transform to success state (checkmark), not 100% bar

### Claude's Discretion (Progress display)
- Progress bar color scheme (single vs per-stage)

### Stage indicators
- Badge/chip showing current stage name
- Step counter in badge (1/5, 2/5, etc.)
- Tooltip reveals remaining stages
- Friendly stage names:
  - Uploading
  - Converting Speech (transcribing)
  - Syncing Timing (aligning)
  - Identifying Speakers (diarizing)
  - Done
- Different badge color per stage (Upload=blue, Processing=yellow, Complete=green, Error=red)

### Connection handling
- Subtle "Reconnecting..." indicator during connection loss, auto-reconnect in background
- After 5 failed attempts (~30 seconds), escalate to visible warning
- Show manual "Reconnect" button after max attempts
- On reconnect, fetch missed updates from backend to sync current state

### Error presentation
- File errors: Toast notification AND inline error state in file row
- Retry button on failed files to re-attempt processing
- User-friendly error messages with "Show details" to reveal technical info
- System-wide errors (server down) get prominent top banner, separate from file errors

</decisions>

<specifics>
## Specific Ideas

- Badge shows step counter like "1/5" with tooltip listing remaining stages
- Smooth progress animation should feel fluid, not jumpy
- Connection loss should not alarm users unnecessarily — subtle indicator first

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-real-time-progress-tracking*
*Context gathered: 2026-01-27*
