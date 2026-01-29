# Project Research Summary

**Project:** WhisperX Transcription App - v1.1 Chunked Uploads
**Domain:** Large file upload for audio/video transcription services
**Researched:** 2026-01-29
**Confidence:** HIGH

## Executive Summary

WhisperX needs to support 500MB+ audio/video files through Cloudflare's 100MB per-request limit. Research shows the proven solution is implementing the TUS resumable upload protocol using **tus-js-client** (frontend) and **tuspyserver** (backend). This approach is battle-tested by Cloudflare Stream, Vimeo, and Supabase, provides automatic resume after network failures, and requires minimal changes to existing architecture.

The recommended implementation keeps the existing react-dropzone UI and WebSocket progress infrastructure unchanged. Files under 100MB continue using the current single-request flow, while larger files are chunked at 50MB per request. The TUS protocol handles all complexity around resumability, retry logic, and session management. The backend tuspyserver library provides a FastAPI router that mounts alongside existing endpoints with post-upload hooks that trigger the existing transcription pipeline.

Critical risks center on Cloudflare compatibility (chunk size must be under 100MB), storage management (orphaned chunks from incomplete uploads), and CORS configuration (TUS headers must be exposed). The research identified 8 table-stakes features users expect for large file uploads, including resume after page refresh, automatic retry, and smooth progress indicators. Implementation can follow a clear four-phase approach that minimizes risk by keeping existing flows intact.

## Key Findings

### Recommended Stack

Research strongly recommends adopting the TUS resumable upload protocol over custom chunking implementations. TUS is an industry standard with mature client and server libraries that handle the edge cases that plague custom implementations.

**Core technologies:**
- **tus-js-client v4.3.1**: Pure JavaScript TUS protocol client with automatic resume, configurable chunk size (set to 50MB), retry delays, and progress callbacks that integrate with existing UI
- **tuspyserver v4.2.3**: FastAPI-native TUS server with dependency injection hooks, built-in cleanup (5-day default expiration), and minimal dependencies (only requires fastapi>=0.110)
- **Existing stack preserved**: React-dropzone continues handling file selection, WebSocket continues handling transcription progress, no UI rewrites required

**Why TUS over custom chunking:**
Custom implementations repeatedly suffer from memory exhaustion (loading all chunks into memory), race conditions (parallel chunk uploads), session state loss (in-memory tracking), and orphaned storage leaks. TUS solves these through standardized protocol headers (Upload-Offset, Location, Tus-Resumable), server-side state management, and proven Cloudflare compatibility when chunks are kept under 100MB.

**Cloudflare constraint:** Chunk size must be configured to 50MB (safe margin under 100MB limit). Files exceeding 512MB may hit Cloudflare's cache reassembly limit, but this is acceptable for WhisperX's target use case.

### Expected Features

Research identified 8 table-stakes features that users expect from chunked upload systems. Missing any of these makes uploads feel broken.

**Must have (table stakes):**
- **Overall file progress bar**: Users need transparent progress to reduce anxiety; chunked uploads without smooth progress feel unresponsive
- **Automatic retry on failure**: Network hiccups are common; system must retry silently (max 3 attempts with exponential backoff) before showing error
- **Resume after page refresh**: Losing 80% of a 500MB upload on accidental browser close is unacceptable; localStorage-based session persistence is required
- **Clear error messages**: "Upload Failed" is useless; errors must be actionable ("Network error. Click to retry")
- **Cancel upload button**: Users must be able to stop uploads immediately without confirmation dialogs
- **Upload speed indicator**: For large files, users want to estimate completion time (show "X MB/s" or "~Y minutes remaining")
- **File size validation before upload**: Prevent wasted time uploading files that exceed server limits
- **Smooth progress updates**: Progress bar must update every 2-3 seconds, not jump in large increments

**Should have (competitive):**
- **Pause/resume button**: User-initiated pause for bandwidth management (defer to v1.2)
- **Background upload via Service Worker**: Upload continues if user navigates away (defer to v1.2)
- **Parallel chunk uploads**: Faster uploads on high-bandwidth connections (defer - adds complexity)

**Defer (v2+):**
- Per-chunk progress visualization (overwhelming for users)
- Chunk size configuration (implementation detail users don't understand)
- Upload history/persistence across sessions (scope creep beyond v1.1)
- Confirmation dialogs on cancel (adds friction; cancel should be immediate and reversible)

**UX pattern:** Progress UI should show two distinct phases: "Uploading... X%" (driven by TUS onProgress callback) followed by "Processing..." (driven by existing WebSocket for transcription stages). Don't try to unify these too early.

### Architecture Approach

The chunked upload system integrates as a parallel flow to the existing single-file upload, reusing most infrastructure.

**Major components:**

1. **TUS Upload Router (Backend)**: New `/uploads/` endpoint mounted in FastAPI that handles TUS protocol negotiation, chunk storage, and automatic cleanup. Uses tuspyserver's built-in dependency injection to trigger transcription after assembly.

2. **Upload Decision Layer (Frontend)**: Modified `useUploadOrchestration.ts` checks file size. Files under 100MB use existing `/speech-to-text` endpoint, files over 100MB use TUS client. Both flows converge at the same WebSocket progress tracking.

3. **Existing Infrastructure (Reused)**: WebSocket ConnectionManager, progress emitter, transcription pipeline, and result delivery remain unchanged. TUS upload completes, triggers existing `process_audio_common` function, everything downstream is identical.

**Integration pattern:**
```
Small file (<100MB):
[react-dropzone] -> [POST /speech-to-text] -> [Transcription] -> [WebSocket Progress]

Large file (>100MB):
[react-dropzone] -> [tus-js-client] -> [POST /uploads/ (TUS)] -> [Assembly Hook] -> [Transcription] -> [WebSocket Progress]
```

**Key decision:** Research explored custom implementation but recommends TUS because the protocol solves session management, resume logic, and retry handling through standardized headers. Custom implementations repeatedly fail on these edge cases.

**CORS requirement:** TUS requires exposing specific headers through Cloudflare (Location, Upload-Offset, Upload-Length, Tus-Resumable). This is a deployment configuration step that's easy to miss.

### Critical Pitfalls

Research identified 14 pitfalls across three severity levels. These are the top 5 that require explicit prevention:

1. **Chunk Assembly Memory Exhaustion**: Loading all chunks into memory before writing the final file causes server crashes with 500MB+ files. TUS prevents this by writing chunks directly to disk and using file system operations for assembly. FastAPI's default `File()` parameter must be avoided.

2. **Cloudflare 100MB Per-Request Limit**: Individual chunk requests larger than 100MB are rejected with 413 error before reaching origin. Solution: Configure `chunkSize: 50 * 1024 * 1024` in tus-js-client (50MB provides safe margin). This is a configuration constant, not user-facing.

3. **Orphaned Chunks Storage Leak**: Incomplete uploads leave chunks on disk forever if cleanup isn't implemented. tuspyserver provides built-in expiration (5-day default) and `remove_expired_files()` function. Schedule this with existing APScheduler infrastructure.

4. **CORS Header Exposure**: Browsers block TUS uploads if response headers aren't exposed through CORS. Cloudflare configuration must include `expose_headers` for TUS protocol headers (Location, Upload-Offset, etc.). Works in development, fails in production if missed.

5. **Cloudflare Rate Limiting False Positives**: Multiple rapid chunk requests from same IP can trigger DDoS protection. A 500MB file with 50MB chunks generates 10 requests in quick succession. Solution: Add WAF rule to exclude `/uploads/` endpoint from rate limiting, or use unproxied subdomain for uploads.

**Phase-specific warnings:**
- **Backend Setup Phase**: Must configure CORS to expose TUS headers before frontend integration
- **Frontend Integration Phase**: Must set chunk size to 50MB; testing with larger chunks will work locally but fail through Cloudflare
- **Deployment Phase**: Cloudflare WAF rules must exclude upload endpoint from rate limiting

**Rejected approach:** Custom chunking using `File.slice()` and manual session tracking. Research shows this requires building session state management, retry logic, resume detection, and assembly validation from scratch. Every one of these has well-documented failure modes (race conditions, memory leaks, off-by-one errors). TUS protocol solves all of these through standardization.

## Implications for Roadmap

Based on research, this feature follows a clear four-phase structure with minimal risk to existing functionality.

### Phase 1: Backend TUS Integration
**Rationale:** Establish upload capability before modifying frontend. Backend can be tested independently with `tus-js-client` in isolation. Keeps existing frontend working throughout.

**Delivers:**
- TUS router mounted at `/uploads/` endpoint
- CORS configuration exposing TUS headers
- Chunk storage and cleanup infrastructure
- Post-upload hook triggering existing transcription pipeline

**Addresses:**
- Cloudflare 100MB limit (chunks configured at 50MB)
- Memory exhaustion (tuspyserver writes chunks to disk)
- Orphaned storage (built-in expiration)

**Avoids:**
- Race conditions (tuspyserver handles state atomically)
- Session state loss (persisted to files_dir)

**Research flags:** Standard implementation following tuspyserver documentation. No additional research needed.

### Phase 2: Frontend TUS Integration
**Rationale:** With backend proven, add frontend TUS client. File size decision layer keeps existing flow working for small files.

**Delivers:**
- tus-js-client integrated with react-dropzone
- File size threshold (100MB) decision logic in `useUploadOrchestration.ts`
- Progress UI showing upload percentage (TUS onProgress callback)
- Resume capability via localStorage fingerprinting

**Uses:**
- tus-js-client v4.3.1 with configured chunk size
- Existing react-dropzone for file selection (no UI changes)
- Existing progress components with new upload phase

**Implements:**
- Upload decision layer (architecture component)
- Two-phase progress (uploading -> processing)

**Avoids:**
- WebSocket state desynchronization (keep upload progress in HTTP layer)
- Off-by-one errors in Content-Range (TUS handles protocol math)

**Research flags:** Standard implementation. TUS client API documentation is comprehensive.

### Phase 3: Resilience & Polish
**Rationale:** With core flow working, add error handling and edge case coverage identified in pitfalls research.

**Delivers:**
- Automatic retry with exponential backoff (TUS retryDelays configuration)
- Clear error messages for permanent failures
- Cancel button integration (abort TUS upload)
- Upload speed and time remaining indicators

**Addresses:**
- Poor error recovery UX (table stakes feature)
- Auto-retry logic (table stakes feature)
- Cancel handling (table stakes feature)

**Avoids:**
- Confirmation dialogs on cancel (anti-feature from research)
- Per-chunk error UI (anti-feature - users don't care which chunk failed)

**Research flags:** Standard patterns covered in feature research. No additional research needed.

### Phase 4: Cloudflare Deployment
**Rationale:** Cloudflare-specific configuration can only be validated in production-like environment. Separate phase ensures testing with actual proxy behavior.

**Delivers:**
- Cloudflare CORS rules for TUS headers
- WAF rule excluding `/uploads/` from rate limiting
- Verification of 50MB chunk size through proxy
- Monitoring for 413 errors (chunk size issues)

**Addresses:**
- Cloudflare rate limiting false positives (critical pitfall)
- CORS header exposure (critical pitfall)

**Avoids:**
- Cloudflare timeout during assembly (tuspyserver handles asynchronously)

**Research flags:** Cloudflare-specific configuration needs validation in staging environment with actual proxy.

### Phase Ordering Rationale

**Why backend-first:** tuspyserver can be tested with curl or standalone TUS client before touching existing frontend. Reduces risk of breaking working upload flow.

**Why decision layer matters:** Files under 100MB continue using existing fast path (`/speech-to-text`). Only large files incur TUS overhead. This preserves current user experience for majority of uploads.

**Why resilience is separate phase:** Core upload-and-transcribe flow must work before adding retry/resume complexity. Easier to debug when error handling is layered on top of working foundation.

**Why Cloudflare configuration is last:** WAF rules and CORS settings can only be validated with production-like traffic patterns. Backend and frontend must be working before introducing proxy-specific issues.

**Dependency insight:** WebSocket progress infrastructure is reused, not modified. Upload progress comes from TUS `onProgress` callback (HTTP), transcription progress comes from existing WebSocket. These are sequential phases, not parallel streams.

### Research Flags

Phases with standard patterns (skip research-phase):
- **Phase 1 (Backend)**: tuspyserver documentation is comprehensive; FastAPI integration is straightforward
- **Phase 2 (Frontend)**: tus-js-client API is well-documented; integration pattern is standard
- **Phase 3 (Resilience)**: Error handling patterns are generic; UX research already captured expectations

Phases needing validation during implementation:
- **Phase 4 (Cloudflare)**: WAF rules and CORS configuration are environment-specific; needs testing in staging with actual proxy before production

**No deep research needed:** This feature is well-understood with mature libraries. Implementation follows established patterns. Cloudflare configuration is documented; just needs hands-on validation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | TUS protocol is mature (2013); tus-js-client and tuspyserver actively maintained; proven Cloudflare compatibility |
| Features | HIGH | Uploadcare, FileStack, and NN/g provide authoritative UX research; feature expectations are consistent across sources |
| Architecture | HIGH | Integration pattern is clean; existing WebSocket and transcription pipeline remain unchanged; parallel flow reduces risk |
| Pitfalls | HIGH | Pitfalls verified across multiple implementations (ownCloud, rclone, TUS-PHP); prevention strategies are proven |

**Overall confidence:** HIGH

### Gaps to Address

Research identified three areas needing attention during implementation:

- **Cloudflare WAF rules**: Documentation describes configuration, but exact rule syntax depends on Cloudflare plan level. Validate in staging before production deployment. Test with multiple file sizes (50MB, 200MB, 500MB) through proxy.

- **Cleanup scheduler timing**: tuspyserver defaults to 5-day expiration. WhisperX usage patterns may warrant shorter TTL (e.g., 24 hours for single-server deployment). Monitor orphaned chunk growth during beta to tune expiration.

- **Resume UX messaging**: Research shows users expect "Resume upload of filename.mp4? (450MB remaining)" prompt, but TUS automatic resume via fingerprinting is silent. Consider whether explicit resume UI adds value or just confusion. Test with real users.

**Validation approach:**
1. Deploy to staging with Cloudflare proxy enabled
2. Test uploads from slow/interrupted connections
3. Monitor chunk storage and cleanup behavior
4. Gather user feedback on resume experience

## Sources

### Primary (HIGH confidence)
- [TUS Protocol Specification](https://tus.io/protocols/resumable-upload) - Resumable upload standard
- [tus-js-client GitHub](https://github.com/tus/tus-js-client) - v4.3.1 release notes and API documentation
- [tuspyserver PyPI](https://pypi.org/project/tuspyserver/) - v4.2.3 documentation
- [tuspyserver GitHub](https://github.com/edihasaj/tuspy-fast-api) - FastAPI integration patterns
- [Cloudflare Connection Limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/) - 100MB request body limit
- [Cloudflare Rate Limiting Best Practices](https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/) - WAF configuration
- [FastAPI Request Files](https://fastapi.tiangolo.com/tutorial/request-files/) - File upload patterns
- [Uploadcare UX Best Practices](https://uploadcare.com/blog/file-uploader-ux-best-practices/) - Upload feature research
- [Google Cloud Resumable Uploads](https://cloud.google.com/storage/docs/resumable-uploads) - Session state management patterns

### Secondary (MEDIUM confidence)
- [Cloudinary Chunked Upload Guidelines](https://support.cloudinary.com/hc/en-us/articles/208263735-Guidelines-for-implementing-chunked-upload-to-Cloudflare) - Content-Range math
- [Cloudflare Community: TUS behind proxy](https://community.cloudflare.com/t/upload-with-tus-protocol-returns-413-for-large-videos-623-mb/603198) - Chunk size confirmation
- [ownCloud Orphaned Chunks Issue](https://github.com/owncloud/core/issues/26981) - Cleanup patterns
- [FastAPI Discussion #9828](https://github.com/fastapi/fastapi/discussions/9828) - Large file upload patterns
- [Transloadit: Chunking and Parallel Uploads](https://transloadit.com/devtips/optimizing-online-file-uploads-with-chunking-and-parallel-uploads/) - Performance patterns

### Tertiary (LOW confidence)
- [Medium: Async File Uploads in FastAPI](https://medium.com/@connect.hashblock/async-file-uploads-in-fastapi-handling-gigabyte-scale-data-smoothly-aec421335680) - Memory management patterns (verify independently)
- [DEV.to: Large File Uploads](https://dev.to/leapcell/how-to-handle-large-file-uploads-without-losing-your-mind-3dck) - General patterns (ecosystem survey only)

---
*Research completed: 2026-01-29*
*Ready for roadmap: yes*
