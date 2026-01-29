# Requirements: WhisperX v1.1

**Defined:** 2026-01-29
**Core Value:** Users can upload large audio/video files (>100MB) through Cloudflare proxy without failures

## v1.1 Requirements

Requirements for chunked upload capability. Enables files up to 500MB through Cloudflare's 100MB per-request limit.

### Backend Infrastructure

- [ ] **BACK-01**: System creates upload session with unique ID when chunked upload starts
- [ ] **BACK-02**: System receives and stores individual chunks (50MB each) to temp directory
- [ ] **BACK-03**: System tracks which chunks received per session
- [ ] **BACK-04**: System assembles chunks into final file when all received
- [ ] **BACK-05**: System triggers existing transcription pipeline after assembly
- [ ] **BACK-06**: System cleans up incomplete sessions after 10 minutes

### Frontend Chunking

- [ ] **FRONT-01**: User drops file and system decides: <100MB uses existing flow, >=100MB uses chunked
- [ ] **FRONT-02**: System splits large files into 50MB chunks using File.slice()
- [ ] **FRONT-03**: System uploads chunks sequentially to backend
- [ ] **FRONT-04**: User sees single progress bar showing overall upload progress (not per-chunk)
- [ ] **FRONT-05**: User sees upload speed in MB/s
- [ ] **FRONT-06**: User sees estimated time remaining

### Resilience

- [ ] **RESIL-01**: System automatically retries failed chunks (3 attempts with exponential backoff)
- [ ] **RESIL-02**: User can cancel upload at any time
- [ ] **RESIL-03**: User can resume interrupted upload after page refresh (via localStorage)
- [ ] **RESIL-04**: System shows clear error message if all retries fail

### Integration

- [ ] **INTEG-01**: Chunked uploads work through Cloudflare proxy without 413 errors
- [ ] **INTEG-02**: Existing WebSocket progress tracking works for transcription after upload
- [ ] **INTEG-03**: Existing file validation (magic bytes) works on assembled file

## Future Requirements

Deferred to v1.2 or later.

### Enhanced UX

- **UX-01**: User can pause and resume uploads manually via button
- **UX-02**: Parallel chunk uploads for faster large file transfers
- **UX-03**: Background upload via Service Worker (upload continues if tab closed)

## Out of Scope

Explicitly excluded from v1.1.

| Feature | Reason |
|---------|--------|
| Per-chunk progress visibility | Confusing UX - users don't care about chunks |
| TUS protocol full implementation | Custom simpler approach sufficient for v1.1 |
| Parallel chunk uploads | Sequential is simpler, parallel adds complexity |
| Background Service Worker | High complexity, defer to future |
| Files >500MB | Cloudflare cache limit, rarely needed |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BACK-01 | Phase 7 | Pending |
| BACK-02 | Phase 7 | Pending |
| BACK-03 | Phase 7 | Pending |
| BACK-04 | Phase 7 | Pending |
| BACK-05 | Phase 7 | Pending |
| BACK-06 | Phase 7 | Pending |
| FRONT-01 | Phase 8 | Pending |
| FRONT-02 | Phase 8 | Pending |
| FRONT-03 | Phase 8 | Pending |
| FRONT-04 | Phase 8 | Pending |
| FRONT-05 | Phase 8 | Pending |
| FRONT-06 | Phase 8 | Pending |
| RESIL-01 | Phase 9 | Pending |
| RESIL-02 | Phase 9 | Pending |
| RESIL-03 | Phase 9 | Pending |
| RESIL-04 | Phase 9 | Pending |
| INTEG-01 | Phase 10 | Pending |
| INTEG-02 | Phase 10 | Pending |
| INTEG-03 | Phase 10 | Pending |

**Coverage:**
- v1.1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0

---
*Requirements defined: 2026-01-29*
*Last updated: 2026-01-29 after roadmap creation*
