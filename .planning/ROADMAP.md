# Roadmap: WhisperX v1.1 Chunked Uploads

## Milestones

- [x] **v1.0 Frontend UI** - Phases 1-6 (shipped 2026-01-29)
- [ ] **v1.1 Chunked Uploads** - Phases 7-10 (in progress)

## Overview

v1.1 enables uploads of files >100MB through Cloudflare's proxy by implementing the TUS resumable upload protocol. The backend receives chunks via tuspyserver, the frontend splits files via tus-js-client, resilience features handle failures gracefully, and Cloudflare configuration ensures production compatibility. Files under 100MB continue using the existing fast path.

## Phases

**Phase Numbering:**
- Integer phases (7, 8, 9, 10): Planned v1.1 work
- Decimal phases (7.1, 7.2): Urgent insertions if needed

- [x] **Phase 7: Backend Chunk Infrastructure** - TUS router, storage, and transcription hook
- [ ] **Phase 8: Frontend Chunking** - TUS client, file size routing, progress UI
- [ ] **Phase 9: Resilience and Polish** - Retry, cancel, resume, error handling
- [ ] **Phase 10: Integration and Deployment** - Cloudflare config, end-to-end validation

## Phase Details

### Phase 7: Backend Chunk Infrastructure
**Goal**: Backend can receive chunked uploads via TUS protocol and trigger transcription
**Depends on**: v1.0 complete (Phase 6)
**Requirements**: BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, BACK-06
**Success Criteria** (what must be TRUE):
  1. POST to /uploads/ creates a new upload session with unique ID returned in Location header
  2. PATCH requests with chunk data are stored to disk (not memory)
  3. When final chunk received, file is assembled and transcription starts automatically
  4. Incomplete upload sessions are cleaned up after 10 minutes
  5. Existing /speech-to-text endpoint continues working unchanged
**Plans**: 3 plans

Plans:
- [x] 07-01-PLAN.md -- TUS router setup with tuspyserver, CORS config, main.py integration
- [x] 07-02-PLAN.md -- Upload session service and transcription trigger hook
- [x] 07-03-PLAN.md -- Session cleanup scheduler with APScheduler

### Phase 8: Frontend Chunking
**Goal**: Large files are automatically chunked and uploaded with unified progress display
**Depends on**: Phase 7
**Requirements**: FRONT-01, FRONT-02, FRONT-03, FRONT-04, FRONT-05, FRONT-06
**Success Criteria** (what must be TRUE):
  1. User drops a 200MB file and sees single smooth progress bar (not per-chunk)
  2. Files under 100MB use existing upload flow (no TUS overhead)
  3. Progress bar shows upload percentage, speed (MB/s), and time remaining
  4. Upload completes and transcription begins automatically
**Plans**: 4 plans

Plans:
- [ ] 08-01-PLAN.md -- TUS library foundation: tus-js-client, upload wrapper, speed tracker, Vite proxy, backend taskId
- [ ] 08-02-PLAN.md -- File size routing: useTusUpload hook, orchestration dual-path routing, taskId handoff
- [ ] 08-03-PLAN.md -- Progress UI: speed/ETA display in FileProgress, human verification
- [ ] 08-04-PLAN.md -- Gap closure: TUS file extension rename + gc_files date parsing fix

### Phase 9: Resilience and Polish
**Goal**: Uploads survive failures and users can control the process
**Depends on**: Phase 8
**Requirements**: RESIL-01, RESIL-02, RESIL-03, RESIL-04
**Success Criteria** (what must be TRUE):
  1. Network blip during upload automatically retries (user sees brief pause, not failure)
  2. User can click cancel and upload stops immediately
  3. User refreshes page mid-upload and can resume from where they left off
  4. If all retries fail, user sees actionable error message (not generic "Upload Failed")
**Plans**: TBD

Plans:
- [ ] 09-01: Retry logic with exponential backoff
- [ ] 09-02: Cancel button and localStorage resume
- [ ] 09-03: Error messaging and edge cases

### Phase 10: Integration and Deployment
**Goal**: Chunked uploads work reliably through Cloudflare in production
**Depends on**: Phase 9
**Requirements**: INTEG-01, INTEG-02, INTEG-03
**Success Criteria** (what must be TRUE):
  1. 500MB file uploads through Cloudflare proxy without 413 errors
  2. After upload completes, WebSocket progress shows transcription stages
  3. Assembled file passes magic byte validation before transcription
**Plans**: TBD

Plans:
- [ ] 10-01: Cloudflare CORS and WAF configuration
- [ ] 10-02: End-to-end testing with various file sizes

## Progress

**Execution Order:** 7 -> 8 -> 9 -> 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 7. Backend Chunk Infrastructure | v1.1 | 3/3 | Complete | 2026-01-29 |
| 8. Frontend Chunking | v1.1 | 0/4 | In progress | - |
| 9. Resilience and Polish | v1.1 | 0/3 | Not started | - |
| 10. Integration and Deployment | v1.1 | 0/2 | Not started | - |

**Total Plans:** 12 (estimate, refined during planning)
**Requirements Coverage:** 19/19 mapped

---
*Roadmap created: 2026-01-29*
*Last updated: 2026-01-31 after Phase 8 UAT gap closure planning*
