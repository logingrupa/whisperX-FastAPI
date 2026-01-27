# Phase 2: File Upload Infrastructure - Context

**Gathered:** 2026-01-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Backend handles large audio/video uploads (up to 5GB) without memory exhaustion or event loop blocking. Validates file formats before processing begins. This is infrastructure that the upload UI (Phase 4) will use.

</domain>

<decisions>
## Implementation Decisions

### Validation Behavior
- Validate early, before upload starts (client-side check on extension/MIME type)
- Accepted formats: MP3, WAV, MP4, M4A, FLAC, OGG, WebM (common formats only)
- Error messages must be specific: "MP3, WAV, MP4, M4A, FLAC, OGG, WebM files only. You uploaded: .xyz"

### Size Limits & Policy
- Maximum file size: 5 GB per file
- Hard reject files over 5GB before upload starts (don't allow selection)
- Total queue limit: 10 GB across all queued files
- Per-file limit enforced client-side, queue limit enforced when adding files

### Upload Feedback
- Show: percentage + speed + ETA + bytes (e.g., "234 MB / 512 MB — 45% — 2.3 MB/s — ~30s remaining")
- Update frequency: time-based, every 500ms
- Cancel button available during upload — aborts transfer

### Failure Handling
- Auto-retry failed chunks 3 times on network failure
- After 3 retries fail: show error + manual retry button + remove option
- Server keeps partial uploads briefly (5-10 minutes) for potential resume
- Timeout: 2 minutes with no progress before considering upload stalled

### Claude's Discretion
- Whether to add magic bytes validation as server-side second layer
- Exact retry backoff strategy (exponential, linear, etc.)
- Chunk size for streaming uploads
- Partial upload cleanup mechanism details

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for streaming upload implementation.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-file-upload-infrastructure*
*Context gathered: 2026-01-27*
