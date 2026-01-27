# Pitfalls Research

**Domain:** React Frontend for FastAPI ML Backend (WhisperX Transcription)
**Researched:** 2026-01-27
**Confidence:** HIGH (verified via official docs, GitHub discussions, community sources)

## Critical Pitfalls

### Pitfall 1: WebSocket Connection State Loss During Long Transcriptions

**What goes wrong:**
WebSocket connections drop silently during long-running ML inference tasks (transcription can take 5-30+ minutes for large files). The React frontend shows stale progress or freezes. Users think the task failed when it is still running on the backend.

**Why it happens:**
- Network infrastructure (routers, firewalls, proxies) terminates idle connections after 30-120 seconds
- FastAPI/Uvicorn has default timeout settings that trigger during gaps between progress updates
- React components unmount/remount (navigation, tab switching) without proper cleanup
- No heartbeat mechanism to keep connections alive during ML processing gaps

**How to avoid:**
1. Implement bidirectional heartbeat (ping/pong) every 15-30 seconds
2. Decouple task state from WebSocket - store progress in Redis/database, WebSocket just broadcasts
3. Use task ID pattern: client polls `/task/{id}/status` as fallback when WebSocket drops
4. Implement `WebSocketDisconnect` exception handling on FastAPI side
5. Add exponential backoff reconnection in React (1s, 2s, 4s... max 30s)

**Warning signs:**
- Progress bar freezes then jumps forward suddenly
- Console shows "WebSocket connection closed unexpectedly"
- Users report "it worked but showed failure message"
- Different behavior in development vs production (proxies add timeouts)

**Phase to address:**
Phase 1 (WebSocket Infrastructure) - Must be foundational before building progress UI

---

### Pitfall 2: Large Audio/Video Uploads Exhausting Memory

**What goes wrong:**
Using `await file.read()` on uploaded audio/video files loads entire file into memory. A single 500MB video upload spikes server memory by 500MB. Under concurrent load, server crashes with OOM errors.

**Why it happens:**
- FastAPI tutorials show simple `file.read()` pattern that works for small files
- Developers test with small files locally, never hitting memory limits
- `UploadFile` spooling limit is small (~1MB by default before disk spillover)
- No explicit chunk size control when iterating uploaded streams

**How to avoid:**
1. Stream uploads chunk-by-chunk using `async for chunk in file` pattern
2. Use `aiofiles` for async disk writes to avoid blocking event loop
3. Set explicit chunk sizes (1-5MB) for processing
4. For very large files (>1GB), use presigned URL pattern - client uploads directly to S3/cloud storage
5. Implement file size validation BEFORE accepting upload

**Warning signs:**
- Server memory spikes correlate with file uploads
- Uploads "work" with small files but fail with large ones
- Concurrent uploads cause cascading failures
- Process killed by OOM killer in production logs

**Phase to address:**
Phase 2 (File Upload Infrastructure) - Must be correct before building upload UI

---

### Pitfall 3: Blocking Event Loop with Synchronous File I/O

**What goes wrong:**
Using synchronous `file.write()` or `shutil.copyfileobj()` in async FastAPI handlers blocks the entire event loop. During a large file write, ALL other requests queue up, causing timeouts and latency spikes.

**Why it happens:**
- Standard Python file I/O is synchronous
- Wrapping sync code in `async def` doesn't make it async - it still blocks
- Most FastAPI file upload tutorials use sync patterns
- Easy to miss in testing when only one request at a time

**How to avoid:**
1. Use `aiofiles` library for all file operations
2. For CPU-bound operations, use `run_in_threadpool` from starlette.concurrency
3. Keep async handlers truly async - no sync blocking code
4. Move heavy file processing to background tasks or Celery workers
5. Load test with concurrent uploads to catch blocking issues

**Warning signs:**
- Single upload causes all API endpoints to slow down
- Response times spike during file processing
- "Request timeout" errors during file operations
- High latency variance under load

**Phase to address:**
Phase 2 (File Upload Infrastructure) - Use async patterns from start

---

### Pitfall 4: React Router 404 on Page Refresh with Embedded SPA

**What goes wrong:**
React app works when navigating via links. User refreshes on `/transcribe/123` and gets 404 from FastAPI. The SPA routes aren't known to the backend, so it tries to find a literal `/transcribe/123` endpoint.

**Why it happens:**
- FastAPI `StaticFiles` mount serves files literally
- React Router handles routes client-side, but refresh hits server first
- No catch-all route configured for SPA fallback
- Developers test navigation without refresh

**How to avoid:**
1. Add 404 exception handler that returns `index.html` for non-API routes:
   ```python
   @app.exception_handler(404)
   async def spa_fallback(request, exc):
       if not request.url.path.startswith("/api"):
           return FileResponse("dist/index.html")
       raise exc
   ```
2. Mount API routes BEFORE static files mount
3. Use path prefix for all API routes (`/api/*`)
4. Test refresh on every frontend route during development

**Warning signs:**
- 404 errors on refresh but not on navigation
- Works in Vite dev server but breaks when served by FastAPI
- Users bookmark pages that return 404 later

**Phase to address:**
Phase 3 (Build Integration) - Configure when embedding frontend

---

### Pitfall 5: FastAPI BackgroundTasks Blocking for ML Inference

**What goes wrong:**
Using FastAPI's built-in `BackgroundTasks` for ML inference (transcription). Tasks run in the same event loop, blocking other requests. No progress tracking, no persistence (server restart loses tasks), no retry mechanism.

**Why it happens:**
- `BackgroundTasks` is easy and built-in, seems like obvious choice
- Works fine for quick tasks (send email, write log)
- ML inference is CPU-bound and long-running - worst case for `BackgroundTasks`
- No status tracking means frontend can't show real progress

**How to avoid:**
1. Use Celery + Redis for all ML inference tasks
2. Or use ARQ (async-native) if already in async ecosystem
3. Never use `BackgroundTasks` for anything taking >5 seconds
4. Implement task status endpoint: `GET /api/tasks/{task_id}/status`
5. Store task state in Redis/database, not in-memory

**Warning signs:**
- API becomes unresponsive during transcription
- Server restart loses in-progress transcriptions
- No way to query task progress from frontend
- Tasks silently fail with no retry

**Phase to address:**
Phase 1 (Task Queue Setup) - Must be foundational infrastructure

---

### Pitfall 6: CORS Misconfiguration Breaking WebSocket in Production

**What goes wrong:**
API calls work, WebSocket connections fail with 403. CORS configured for HTTP but not WebSocket. Works in development (same origin), breaks in production or when ports differ.

**Why it happens:**
- WebSocket upgrade request is a regular HTTP request first
- CORS must allow WebSocket handshake origin
- Middleware order matters - CORS must be added first
- 500 errors in handlers bypass CORS headers entirely
- Using wildcard `*` in development but forgetting to configure production

**How to avoid:**
1. Configure CORS middleware with explicit origins (not `*` in production):
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://yourdomain.com"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```
2. Add CORS middleware FIRST (before other middleware)
3. Test WebSocket connections with production CORS settings locally
4. Better: Serve frontend from same origin (embedded) to avoid CORS entirely

**Warning signs:**
- "Failed to connect to WebSocket: HTTP 403"
- Works locally but fails when deployed
- HTTP endpoints work but WebSocket fails
- CORS headers present on success but missing on errors

**Phase to address:**
Phase 1 (WebSocket Infrastructure) - Configure with initial WebSocket setup

---

### Pitfall 7: Progress Tracking Desync Between Backend and Frontend

**What goes wrong:**
Frontend shows 70% progress, but backend already completed (or failed). Progress updates arrive out of order or are lost. UI flickers between progress states. Task completes but frontend never updates.

**Why it happens:**
- WebSocket messages can arrive out of order
- No sequence numbers or timestamps on progress updates
- React state updates batch unexpectedly with rapid messages
- Network latency causes stale updates to arrive after final state
- No reconciliation when WebSocket reconnects

**How to avoid:**
1. Include monotonic sequence number in every progress message
2. Discard messages with sequence < last received
3. On reconnect, fetch full state snapshot before resuming stream
4. Use React's `useReducer` instead of `useState` for complex state
5. Backend should always send final state (complete/failed) even if client appears disconnected

**Warning signs:**
- Progress bar jumps backwards sometimes
- Final state doesn't match progress shown
- Different browsers/tabs show different progress for same task
- "Race condition" bugs that are hard to reproduce

**Phase to address:**
Phase 4 (Progress UI) - Design state protocol before building UI

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `file.read()` for uploads | Simple code | Memory exhaustion at scale | Never for audio/video files |
| In-memory WebSocket connections | No Redis dependency | Single-process only, no scaling | Development only |
| `BackgroundTasks` for inference | No Celery setup | Blocks event loop, no persistence | Never for ML tasks |
| Wildcard CORS (`*`) | Quick fix for CORS errors | Security vulnerability, credential issues | Development only |
| Polling instead of WebSocket | Simpler implementation | Higher latency, server load | Acceptable as fallback |
| Single-file React bundle | Simple deployment | Slow initial load for large apps | MVP only, refactor for production |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Vite + FastAPI | Building frontend but not copying `dist/` to container | Multi-stage Docker build, copy dist in final stage |
| React Router + StaticFiles | No catch-all for SPA routes | 404 handler returns index.html for non-API paths |
| WebSocket + Celery | Trying to send WebSocket from Celery worker | Celery updates Redis/DB, FastAPI broadcasts via WebSocket |
| Presigned URLs + Large Files | Generating URL after receiving file | Generate URL first, client uploads directly to S3 |
| Uvicorn + File Uploads | Default timeout too short | Configure `--timeout-keep-alive` and proxy timeouts |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading full file to memory | OOM crashes | Stream in chunks | >100MB files or >3 concurrent uploads |
| Sync file I/O in async handlers | Request queue backup | Use aiofiles | >2 concurrent file operations |
| Single-process WebSocket manager | WebSocket works but not across pods | Use Redis pub/sub for connection manager | Horizontal scaling (>1 replica) |
| No connection limits | Server overwhelmed | Set max WebSocket connections | >100 concurrent users |
| Huge progress update frequency | Frontend thrashing | Throttle to max 2-4 updates/second | Long transcriptions with many segments |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| CORS wildcard in production | Any site can call your API | Explicit origin allowlist |
| No file type validation | Arbitrary file upload attacks | Validate MIME type AND file extension AND magic bytes |
| No file size limits | DoS via huge uploads | Reject before reading: check Content-Length header |
| Task IDs as sequential integers | Task enumeration/scraping | Use UUIDs for task IDs |
| WebSocket without auth | Unauthorized access to progress | Validate JWT/session on WebSocket connect |
| Storing uploads in web-accessible path | Direct file access bypassing API | Store uploads outside of static files directory |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No upload progress indicator | User thinks upload is broken | Show upload percentage before processing starts |
| Single "Processing..." state | User has no idea how long to wait | Show stages: "Uploading", "Queued", "Transcribing (45%)", "Finalizing" |
| Losing state on refresh | User loses progress context | Persist task ID in URL, restore state on load |
| No error details on failure | User can't retry correctly | Show specific error: "File too large" vs "Unsupported format" vs "Server error" |
| Blocking UI during long operations | Frustrated users | Allow browsing/starting other tasks while one processes |
| No cancellation option | Stuck watching unwanted task | Add cancel button that actually terminates background task |

## "Looks Done But Isn't" Checklist

- [ ] **File Upload:** Often missing size limits - verify max file size is enforced BEFORE reading
- [ ] **WebSocket:** Often missing reconnection logic - verify automatic reconnect after disconnect
- [ ] **Progress Tracking:** Often missing error state - verify failed tasks show failure in UI
- [ ] **Task Queue:** Often missing cleanup - verify completed tasks are cleaned up from Redis
- [ ] **Static Files:** Often missing cache headers - verify production cache-control headers set
- [ ] **Error Handling:** Often missing logging - verify errors are logged server-side with context
- [ ] **CORS:** Often missing credentials - verify `allow_credentials=True` if using cookies/auth
- [ ] **Docker Build:** Often missing .dockerignore - verify node_modules and __pycache__ excluded

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Memory exhaustion from file reads | LOW | Refactor to streaming pattern, restart server |
| Lost tasks from BackgroundTasks | MEDIUM | Migrate to Celery, replay failed tasks from logs |
| Broken React routes | LOW | Add SPA fallback handler, redeploy |
| WebSocket state desync | MEDIUM | Add sequence numbers, implement reconciliation on reconnect |
| CORS blocking production | LOW | Update allowed origins, redeploy |
| Blocked event loop | MEDIUM | Audit all sync code, migrate to aiofiles/threadpool |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| WebSocket connection drops | Phase 1: WebSocket Infrastructure | Test 30+ minute connection with no activity |
| Memory exhaustion on upload | Phase 2: File Upload | Upload 1GB file while running memory profiler |
| Event loop blocking | Phase 2: File Upload | Load test: 10 concurrent uploads, measure p99 latency |
| React Router 404 | Phase 3: Build Integration | Refresh on every frontend route, verify no 404 |
| BackgroundTasks for ML | Phase 1: Task Queue Setup | Restart server during task, verify task resumes |
| CORS for WebSocket | Phase 1: WebSocket Infrastructure | Test WebSocket from different origin |
| Progress desync | Phase 4: Progress UI | Rapidly send 100 progress updates, verify UI consistency |

## Sources

**Official Documentation:**
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)
- [FastAPI Static Files](https://fastapi.tiangolo.com/tutorial/static-files/)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)

**GitHub Discussions & Issues:**
- [WebSocket timeout issues](https://github.com/fastapi/fastapi/discussions/11340)
- [React Router 404 on refresh](https://github.com/fastapi/fastapi/discussions/11502)
- [BackgroundTasks blocking application](https://github.com/fastapi/fastapi/discussions/11210)
- [Uploading large files](https://github.com/fastapi/fastapi/discussions/9828)
- [Streaming file uploads](https://github.com/fastapi/fastapi/issues/2578)

**Community Guides:**
- [Serving React with FastAPI](https://davidmuraya.com/blog/serving-a-react-frontend-application-with-fastapi/)
- [FastAPI File Uploads](https://davidmuraya.com/blog/fastapi-file-uploads/)
- [Celery Progress with FastAPI](https://celery.school/celery-progress-bars-with-fastapi-htmx)
- [FastAPI Background Tasks vs ARQ](https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/)
- [WebSocket Reconnection Strategies](https://dev.to/hexshift/robust-websocket-reconnection-strategies-in-javascript-with-exponential-backoff-40n1)
- [React WebSocket Best Practices](https://maybe.works/blogs/react-websocket)
- [Chunked File Uploads Guide](https://arnabgupta.hashnode.dev/mastering-chunked-file-uploads-with-fastapi-and-nodejs-a-step-by-step-guide)
- [TUS Resumable Uploads](https://tus.io/)

---
*Pitfalls research for: React Frontend + FastAPI ML Backend (WhisperX)*
*Researched: 2026-01-27*
