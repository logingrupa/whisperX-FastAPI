# Phase 8: Frontend Chunking - Context

**Gathered:** 2026-01-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Large files are automatically chunked and uploaded via TUS protocol with unified progress display. Files under the threshold use the existing direct upload path. The user experience is identical regardless of upload path. Multi-file uploads are supported sequentially. Resilience features (retry, resume, cancel) are Phase 9.

</domain>

<decisions>
## Implementation Decisions

### Size threshold behavior
- Threshold set at 80MB (files >= 80MB use TUS chunked upload, below use direct)
- Routing is invisible to the user — same UI regardless of which path is used
- No maximum file size limit — TUS handles arbitrarily large files
- No warning for very large files — progress bar communicates duration naturally

### Progress display
- Show percentage, speed (MB/s), and estimated time remaining
- Progress bar is identical for both direct and chunked uploads — same visual, same stats
- Upload progress fills to 100%, then switches to transcription status (clear separation)
- Reuse/adapt existing v1.0 progress UI component — not a new component

### File drop experience
- Upload starts immediately on drop — no confirmation step
- Accept multiple files at once
- Multiple files upload sequentially (one at a time, in order)
- Client-side file type validation before upload starts — reject invalid types immediately with feedback

### Transcription handoff
- After upload hits 100%, show brief "Upload complete!" state for 1-2 seconds, then transition to transcription progress
- Transcription of file 1 starts while file 2 is still uploading (overlap processing)
- Each file in the queue shows its own individual status (uploading, processing, complete)
- Reuse existing WebSocket connection for transcription progress — same infrastructure as v1.0

### Claude's Discretion
- Exact chunk size for TUS uploads (research decision was 50MB, adjust if needed)
- How to adapt existing progress component for multi-file display
- Exact file type validation rules (match what server already accepts)
- Animation/transition details between upload and transcription states

</decisions>

<specifics>
## Specific Ideas

- Multi-file support with individual status per file — user should see a list of files each with their own progress/state
- Sequential upload with overlapping transcription — file 1 can be transcribing while file 2 uploads
- Brief "Upload complete!" celebration moment before transcription kicks in

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-frontend-chunking*
*Context gathered: 2026-01-29*
