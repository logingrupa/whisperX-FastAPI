# Phase 1: WebSocket & Task Infrastructure - Context

**Gathered:** 2026-01-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Backend foundation for real-time progress updates. WebSocket endpoint accepts connections, maintains them during long transcription operations (5-30 minutes), and pushes progress updates to clients. Includes heartbeat mechanism and fallback polling endpoint. This is infrastructure — UI components that display progress are Phase 5.

</domain>

<decisions>
## Implementation Decisions

### Connection handling
- Automatic reconnection with exponential backoff (immediate, then 1s, 2s, 4s...)
- Maximum 5 reconnection attempts before showing manual "Reconnect" button
- Connection status always visible in UI (Connected/Connecting/Disconnected indicator)

### Progress message format
- No ETA — just percentage and stage (estimates are unreliable for transcription)
- Error messages at both levels: user-friendly message + expandable technical detail with error code
- Stages: Uploading, Queued, Transcribing, Aligning, Diarizing, Complete

### Heartbeat design
- 30-second heartbeat interval (stays under typical 60s proxy timeouts)

### Claude's Discretion
- Percentage granularity (whole numbers vs decimals)
- Stage sub-descriptions (e.g., "Processing segment 3 of 10")
- Ping direction (server-initiated, client-initiated, or bidirectional)
- Ping visibility (application-level JSON vs protocol-level ping/pong)
- Timeout tolerance (1 vs 2 missed pings before declaring dead)
- Catch-up behavior after reconnection (request last state or just continue)

### Fallback polling
- Claude decides when to trigger fallback (likely after reconnection exhausted)
- Claude decides polling interval (balance UX vs server load)
- Claude decides recovery behavior (whether to retry WebSocket while polling)
- Claude decides mode indicator visibility (whether UI shows "Live" vs "Polling")

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for WebSocket infrastructure.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-websocket-task-infrastructure*
*Context gathered: 2026-01-27*
