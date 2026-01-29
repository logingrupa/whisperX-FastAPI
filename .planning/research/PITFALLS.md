# Pitfalls Research: Chunked File Uploads

**Domain:** Chunked file uploads for large media files through Cloudflare proxy
**Context:** Adding chunked uploads to existing WhisperX transcription app (FastAPI + React + WebSocket)
**Researched:** 2026-01-29
**Confidence:** HIGH (verified across multiple authoritative sources)

---

## Critical Pitfalls

Mistakes that cause data corruption, upload failures, or require architectural rewrites.

### 1. Chunk Assembly Memory Exhaustion

**What goes wrong:** Loading all chunks into memory before writing the final file causes server crashes with large files (500MB+). FastAPI's default `File()` parameter loads entire files into memory.

**Why it happens:** Developers use the intuitive approach of collecting all chunks in memory, then writing once. Works in development with small files, catastrophic in production.

**Consequences:**
- Server runs out of memory and crashes
- Other users' requests fail during assembly
- Uvicorn worker killed by OOM, no graceful error to client

**Warning signs:**
- Memory usage spikes during final chunk upload
- Server becomes unresponsive during assembly phase
- Works with 50MB files, fails with 200MB files

**Prevention:**
- Write each chunk directly to disk as it arrives using `aiofiles`
- Use `request.stream()` instead of `UploadFile` for streaming writes
- Final assembly: use file system append operations, not memory concatenation
- Consider streaming chunks directly to final file position using seek operations

**Phase:** Address in initial chunk upload endpoint implementation

**Source:** [FastAPI File Upload Discussion](https://github.com/fastapi/fastapi/discussions/9828), [Async File Uploads in FastAPI](https://medium.com/@connect.hashblock/async-file-uploads-in-fastapi-handling-gigabyte-scale-data-smoothly-aec421335680)

---

### 2. Race Conditions in Parallel Chunk Uploads

**What goes wrong:** When multiple chunks upload simultaneously, concurrent writes to tracking state or the same file cause data corruption.

**Why it happens:** Frontend sends chunks in parallel for speed. Without proper synchronization, two threads may:
- Update the same offset counter simultaneously
- Write to overlapping file positions
- Report conflicting completion status

**Consequences:**
- Corrupted files that play partially or have artifacts
- Missing chunks in final file (looks complete but isn't)
- SHA256 checksum mismatches
- Silent corruption (worst case - file "works" but is damaged)

**Warning signs:**
- Intermittent checksum failures
- Audio/video has glitches at chunk boundaries
- File size correct but content wrong
- Issue appears only under load or with fast connections

**Prevention:**
- Use mutex/lock when updating upload session state
- Each chunk writes to its own temporary file, merge sequentially at end
- Verify chunk count and total bytes before marking complete
- Use atomic file operations where possible
- Consider ordered upload (chunk N+1 waits for N) for simplicity over parallelism

**Phase:** Address in chunk upload endpoint design

**Source:** [TUS-PHP Race Condition Issue](https://github.com/ankitpokhrel/tus-php/issues/257), [rclone Azure Race Condition](https://github.com/rclone/rclone/issues/7590)

---

### 3. Off-by-One Errors in Content-Range Headers

**What goes wrong:** Content-Range header math is incorrect, causing chunks to be misaligned or rejected.

**Why it happens:** Content-Range uses inclusive byte ranges. `bytes 0-5999999/22744222` means bytes 0 through 5,999,999 (6MB total), not 6,000,001 bytes.

**Consequences:**
- Server rejects chunks with 400 Bad Request
- Chunks overlap, creating duplicated data
- Chunks have gaps, creating missing data
- File appears complete but has subtle corruption

**Warning signs:**
- "Invalid Content-Range" errors
- Final file size doesn't match original
- Checksum always fails
- First and last chunks work, middle chunks fail

**Prevention:**
```javascript
// Correct calculation
const start = chunkIndex * chunkSize;
const end = Math.min(start + chunkSize - 1, totalSize - 1); // -1 for inclusive
const contentRange = `bytes ${start}-${end}/${totalSize}`;
```
- Write explicit unit tests for boundary conditions
- Test with file sizes that are exact multiples of chunk size
- Test with file sizes that have a small remainder chunk

**Phase:** Address in frontend chunk upload implementation

**Source:** [Cloudinary Chunked Upload Guidelines](https://support.cloudinary.com/hc/en-us/articles/208263735-Guidelines-for-implementing-chunked-upload-to-Cloudinary)

---

### 4. Orphaned Chunks Storage Leak

**What goes wrong:** Incomplete uploads leave chunks on disk forever, slowly filling storage.

**Why it happens:** User closes browser, network fails, or client crashes mid-upload. Server has partial chunks but no cleanup trigger.

**Consequences:**
- Disk fills up over time
- Storage costs increase (if using cloud storage)
- No visibility into orphaned data
- Manual cleanup becomes operational burden

**Warning signs:**
- Disk usage grows faster than completed uploads
- Many directories in temp upload folder with old timestamps
- Storage alerts without corresponding increase in completed files

**Prevention:**
- Store upload session creation timestamp
- Run background cleanup job (every hour or daily)
- Delete sessions older than threshold (24 hours is reasonable)
- Track session expiry in database, not just filesystem
- Log cleanup operations for monitoring
- Consider upload session TTL in database with automatic expiry

**Phase:** Address in upload session management and background tasks

**Source:** [ownCloud Orphaned Chunks Issue](https://github.com/owncloud/core/issues/26981), [AWS S3 Multipart Cleanup](https://kb.msp360.com/cloud-vendors/amazon-aws/removing-incomplete-multipart-uploads-chunks-with-a-lifecycle-policy)

---

### 5. Upload Session State Loss

**What goes wrong:** Server loses track of which chunks have been received, requiring re-upload of entire file.

**Why it happens:**
- Session state stored only in memory (lost on server restart)
- Redis/database connection fails
- Load balancer routes chunks to different servers without sticky sessions
- Session token expires mid-upload

**Consequences:**
- Users must restart large uploads from scratch
- Frustration and abandonment for 500MB+ files
- Wasted bandwidth

**Warning signs:**
- Uploads fail after server deployments
- Resuming upload reports "session not found"
- Works in development, fails in production with multiple servers

**Prevention:**
- Persist session state to database, not memory
- Include received chunk bitmap in session
- For WhisperX (single server): SQLite or filesystem-based state is acceptable
- Store: upload_id, total_size, chunk_size, received_chunks[], created_at, expires_at
- Implement HEAD endpoint to query upload status for resumability

**Phase:** Address in upload session design

**Source:** [Google Cloud Resumable Uploads](https://cloud.google.com/storage/docs/resumable-uploads), [Box Chunked Uploads](https://developer.box.com/guides/uploads/chunked)

---

## Cloudflare-Specific Pitfalls

Issues specific to running behind Cloudflare proxy.

### 6. Cloudflare 100MB Per-Request Limit

**What goes wrong:** Individual chunk requests larger than 100MB are rejected with 413 error.

**Why it happens:** Cloudflare Free/Pro plans have hard 100MB request body limit. This applies to each chunk request, not the total file.

**Consequences:**
- Large chunks rejected before reaching origin server
- Confusing error for users (appears server-side but is proxy)
- Chunked upload "works" but with artificially small chunks

**Warning signs:**
- 413 Request Entity Too Large from Cloudflare (not your server)
- Error occurs instantly (Cloudflare edge), not after transfer
- Works when bypassing Cloudflare

**Prevention:**
- Set chunk size to 50MB or less (safe margin under 100MB)
- Document chunk size limit in frontend configuration
- Return clear error message if chunk exceeds limit
- Consider 20-25MB chunks for reliability over speed

**Phase:** Address in chunk size configuration (both frontend and backend)

**Source:** [Cloudflare Connection Limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/), [Cloudflare Upload Limit Discussion](https://community.cloudflare.com/t/unable-to-upload-big-file-on-cloudflare-using-proxy/498774)

---

### 7. Cloudflare Rate Limiting False Positives

**What goes wrong:** Cloudflare blocks chunked uploads as suspected DDoS attack.

**Why it happens:** Multiple rapid requests from same IP (one per chunk) triggers rate limiting rules. A 500MB file with 10MB chunks = 50 requests in quick succession.

**Consequences:**
- User blocked mid-upload with 429 error
- Upload fails and cannot resume (session may expire during block)
- Legitimate users treated as attackers

**Warning signs:**
- Uploads fail after ~10-20 chunks
- 429 Too Many Requests error
- Works with small files, fails with large files
- Issue appears for fast uploaders on good connections

**Prevention:**
- Configure Cloudflare rate limiting to exclude upload endpoints
- Use WAF rule: `http.request.uri.path contains "/upload"` to bypass rate limit
- Alternatively, add upload endpoint to allowed list
- Consider using unproxied subdomain for uploads (e.g., `upload.example.com` DNS-only)
- Add small delay between chunk uploads if rate limiting unavoidable

**Phase:** Address in Cloudflare configuration during deployment

**Source:** [Cloudflare Rate Limiting Best Practices](https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/), [Rate Limiting Behavior Discussion](https://community.cloudflare.com/t/rate-limiting-behavior/695221)

---

### 8. Cloudflare Timeout During Long Assembly

**What goes wrong:** Cloudflare times out the connection while server assembles final file.

**Why it happens:** After last chunk uploads, server may take 30+ seconds to:
- Verify all chunks
- Concatenate files
- Calculate checksum
- Move to final location

Cloudflare has connection timeout limits.

**Consequences:**
- Client receives timeout error despite successful upload
- File is assembled but client doesn't know
- Retry logic re-uploads unnecessarily

**Warning signs:**
- Uploads "fail" but files appear on server
- Timeout occurs at 100% upload progress
- Larger files fail more often

**Prevention:**
- Return 202 Accepted immediately after last chunk, assemble asynchronously
- Use existing WebSocket infrastructure to report assembly progress
- Send heartbeats during assembly to keep connection alive
- Separate "upload complete" from "file ready" status
- Add `/upload/{id}/status` endpoint to check assembly progress

**Phase:** Address in upload completion flow design

**Source:** [Cloudflare Workers Limits](https://developers.cloudflare.com/workers/platform/limits/)

---

## Common Mistakes

Frequently made errors that cause bugs or poor user experience.

### 9. Missing Chunk Order Validation

**What goes wrong:** Server accepts chunks out of order but assembles them in arrival order, not logical order.

**Why it happens:** Network latency varies. Chunk 5 may arrive before chunk 4. Simple append-based assembly corrupts the file.

**Consequences:**
- Corrupted files
- Audio/video plays but is scrambled
- Checksum fails

**Warning signs:**
- File corruption is intermittent
- Small files work, large files sometimes fail
- Fast connections have more issues (chunks arrive out of order)

**Prevention:**
- Store chunk index with each chunk
- Name temp files with chunk index: `upload_abc_chunk_003.tmp`
- Assemble by sorting chunk indices, not arrival time
- Validate all chunks present before assembly (no gaps)

**Phase:** Address in chunk storage and assembly logic

**Source:** [Cloudinary Guidelines](https://support.cloudinary.com/hc/en-us/articles/208263735-Guidelines-for-implementing-chunked-upload-to-Cloudinary)

---

### 10. No Client-Side Chunk Integrity Verification

**What goes wrong:** Network corruption goes undetected, resulting in corrupted uploads.

**Why it happens:** Developer assumes TCP guarantees integrity (it mostly does, but edge cases exist). No checksum verification per chunk.

**Consequences:**
- Silent file corruption
- Transcription fails or produces garbage
- User blames app, not network

**Warning signs:**
- Rare, intermittent file corruption
- Users on mobile/spotty networks have more issues
- Files "look fine" but don't process correctly

**Prevention:**
- Calculate MD5 or SHA256 of each chunk on client
- Send hash in `X-Chunk-Checksum` header
- Server verifies hash before accepting chunk
- Reject and request retry if mismatch
- For extra safety: full file checksum after assembly

**Phase:** Address in chunk upload protocol (both frontend and backend)

**Source:** [AWS S3 Object Integrity](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html), [TUS Protocol Checksum Extension](https://tus.io/protocols/resumable-upload)

---

### 11. Poor Error Recovery UX

**What goes wrong:** Any error requires full re-upload instead of resuming from last successful chunk.

**Why it happens:** Frontend doesn't track which chunks succeeded. Backend doesn't provide query endpoint for upload state.

**Consequences:**
- Users give up on large uploads
- Bandwidth wasted on re-uploads
- Perception of unreliable product

**Warning signs:**
- Support complaints about upload failures
- High abandonment rate for large files
- Users upload same file multiple times

**Prevention:**
- Frontend: track successful chunk indices locally (localStorage)
- Backend: provide `GET /upload/{id}/status` endpoint returning received chunks
- On resume: query status, upload only missing chunks
- Show clear "Resuming from X%" message to user
- Store upload state even across browser refresh

**Phase:** Address in upload session management and frontend retry logic

**Source:** [TUS Protocol](https://tus.io/protocols/resumable-upload)

---

### 12. WebSocket State Desynchronization

**What goes wrong:** Upload progress shown via WebSocket gets out of sync with actual chunk upload state.

**Why it happens:** WhisperX uses WebSocket for transcription progress. Adding upload progress to same WebSocket creates complexity:
- Upload progress comes from HTTP chunk responses
- Transcription progress comes from WebSocket
- Mixing sources causes confusion

**Consequences:**
- Progress bar jumps backward
- Completion announced before upload finished
- User confusion about actual status

**Warning signs:**
- Progress bar not smooth
- "Complete" shown but file still uploading
- Frontend console shows state conflicts

**Prevention:**
- Keep upload progress in HTTP layer (XHR progress events)
- WebSocket only for transcription/processing progress (current design)
- Clear state machine: uploading (HTTP) -> processing (WebSocket) -> complete
- Don't try to unify progress reporting too early

**Phase:** Address in frontend state management design

**Source:** Existing WhisperX codebase analysis (`useUploadOrchestration.ts`)

---

### 13. First Chunk Special Handling Forgotten

**What goes wrong:** First chunk initializes upload session, but code treats all chunks identically.

**Why it happens:** First chunk typically:
- Creates upload session
- Validates total file size
- Returns upload ID for subsequent chunks

Treating it like other chunks breaks the flow.

**Consequences:**
- Upload ID not available for chunks 2+
- Duplicate session creation
- Wasted server resources

**Warning signs:**
- Each chunk creates new session
- Backend shows many orphaned single-chunk sessions
- Chunk 2 returns "session not found"

**Prevention:**
- Explicit flow: `POST /upload/init` -> returns `upload_id`
- All chunks include `upload_id` in URL or header
- First chunk CAN include data, but session creation is separate concern
- Alternative: first chunk has different endpoint or header flag

**Phase:** Address in API endpoint design

**Source:** [Cloudinary Guidelines](https://support.cloudinary.com/hc/en-us/articles/208263735-Guidelines-for-implementing-chunked-upload-to-Cloudinary)

---

### 14. Insufficient Logging for Debugging

**What goes wrong:** Upload failures are undebuggable in production.

**Why it happens:** Chunked uploads have many failure points. Without detailed logging:
- Can't identify which chunk failed
- Can't reproduce timing issues
- Can't distinguish client vs server vs network issues

**Consequences:**
- Support tickets unresolvable
- Same issues keep recurring
- Frustrated users and developers

**Warning signs:**
- "Upload failed" with no actionable detail
- Can't reproduce reported issues
- Different behavior in dev vs production

**Prevention:**
Log at each step:
- Session creation: upload_id, total_size, chunk_size, client_info
- Each chunk: upload_id, chunk_index, received_bytes, duration, checksum
- Assembly: upload_id, chunks_count, final_size, assembly_duration
- Errors: upload_id, chunk_index, error_type, error_detail

Include correlation ID (upload_id) in all logs for filtering.

**Phase:** Address throughout implementation

---

## Prevention Strategies Summary

| Pitfall | Prevention Strategy | Phase |
|---------|---------------------|-------|
| Memory exhaustion | Stream to disk, never hold in memory | Chunk endpoint |
| Race conditions | Mutex on session state, separate chunk files | Chunk endpoint |
| Off-by-one Content-Range | Unit tests for boundary math | Frontend upload |
| Orphaned chunks | Background cleanup job with TTL | Background tasks |
| Session state loss | Persist to database, not memory | Session management |
| Cloudflare 100MB limit | 50MB chunk size max | Configuration |
| Cloudflare rate limiting | WAF rule to exclude upload endpoint | Deployment |
| Assembly timeout | Async assembly, return 202 immediately | Completion flow |
| Chunk order corruption | Index-based storage and assembly | Storage logic |
| No integrity verification | Checksum per chunk | Protocol design |
| Poor error recovery | Resume endpoint, localStorage tracking | Frontend + API |
| WebSocket desync | HTTP for upload, WebSocket for processing | State management |
| First chunk special handling | Explicit session init endpoint | API design |
| Insufficient logging | Structured logs with upload_id correlation | Throughout |

---

## Recommended Protocol: TUS vs Custom

Based on research, two viable approaches:

### Option 1: TUS Protocol (Recommended for complex cases)
- Battle-tested, used by Cloudflare, Vimeo, Supabase
- Handles resumability, checksums, expiration
- Python server: `tusd` or `tus-py-client`
- More complexity but proven reliability

### Option 2: Custom Implementation (Acceptable for WhisperX scope)
- Simpler, tailored to exact needs
- Full control over behavior
- Less code to maintain if kept minimal
- Risk: reinventing solved problems

**Recommendation for WhisperX:** Custom implementation is acceptable given:
- Single server deployment (no distributed state issues)
- Known, controlled client (own frontend)
- Existing WebSocket infrastructure for progress
- Simpler operational model

If issues arise, TUS can be adopted later.

---

## Sources

**Authoritative:**
- [TUS Resumable Upload Protocol](https://tus.io/protocols/resumable-upload)
- [Cloudflare Connection Limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/)
- [Cloudflare Rate Limiting Best Practices](https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/)
- [AWS S3 Object Integrity](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html)
- [Google Cloud Resumable Uploads](https://cloud.google.com/storage/docs/resumable-uploads)
- [FastAPI Request Files Documentation](https://fastapi.tiangolo.com/tutorial/request-files/)

**Community/Implementation:**
- [FastAPI Large File Upload Discussion](https://github.com/fastapi/fastapi/discussions/9828)
- [Cloudinary Chunked Upload Guidelines](https://support.cloudinary.com/hc/en-us/articles/208263735-Guidelines-for-implementing-chunked-upload-to-Cloudinary)
- [ownCloud Orphaned Chunks Issue](https://github.com/owncloud/core/issues/26981)
- [TUS-PHP Race Condition Issue](https://github.com/ankitpokhrel/tus-php/issues/257)
- [rclone Azure Race Condition](https://github.com/rclone/rclone/issues/7590)
- [Box Chunked Uploads Guide](https://developer.box.com/guides/uploads/chunked)
- [Transloadit Chunking Guide](https://transloadit.com/devtips/optimizing-online-file-uploads-with-chunking-and-parallel-uploads/)
