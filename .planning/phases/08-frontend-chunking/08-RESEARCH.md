# Phase 8: Frontend Chunking - Research

**Researched:** 2026-01-29
**Domain:** TUS client integration in React, upload progress with speed/ETA, file size routing
**Confidence:** HIGH

## Summary

This phase integrates tus-js-client into the existing React frontend to handle large file uploads via the TUS resumable upload protocol. Files >= 80MB are routed through TUS chunked uploads while files < 80MB continue using the existing direct `POST /speech-to-text` flow. The user experience must be identical regardless of path: a single progress bar with percentage, speed (MB/s), and estimated time remaining.

The primary technical challenge is the **task ID handoff**: the existing direct upload flow returns a task ID in the API response, which the frontend uses for WebSocket progress subscription. The TUS protocol returns `204 No Content` on completion with no task ID. The backend completion hook creates the task and returns its ID, but tuspyserver discards this return value. The frontend must obtain the task ID through an alternative mechanism.

The secondary challenge is computing upload speed and ETA from raw `(bytesSent, bytesTotal)` values provided by tus-js-client's `onProgress` callback, which requires smoothing to avoid jittery displays.

**Primary recommendation:** Use tus-js-client v4.3.1 directly (not the `use-tus` wrapper), send task metadata including a pre-generated correlation ID via TUS metadata, and use that correlation ID to poll or subscribe for the backend-assigned task ID after upload completion.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **tus-js-client** | 4.3.1 | TUS resumable upload client | Official TUS protocol client, TypeScript support built-in, browser-optimized, handles chunking internally |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **react-dropzone** | 14.3.8 (existing) | File drop and selection | Already in project, continues to handle file acceptance |
| **react-use-websocket** | 4.13.0 (existing) | WebSocket for transcription progress | Already handles transcription progress, reuse for TUS uploads |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tus-js-client directly | use-tus (React hook wrapper) | use-tus has 119 GitHub stars, unclear v4 compatibility, adds abstraction layer over simple API. tus-js-client is straightforward enough to wrap in a custom hook |
| tus-js-client directly | Uppy | Full UI framework with TUS support, but replaces react-dropzone and adds massive dependency. Overkill when we already have UI components |
| Custom speed/ETA calculation | No library exists | tus-js-client provides raw bytes only; speed/ETA must be hand-calculated. This is the correct approach -- it's simple math, not a library problem |

**Installation:**
```bash
cd frontend && npm install tus-js-client
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
  hooks/
    useUploadOrchestration.ts   # MODIFY: Add file size routing and TUS path
    useTusUpload.ts             # NEW: TUS upload hook wrapping tus-js-client
    useUploadProgress.ts        # NEW: Speed/ETA calculation from raw bytes
    useFileQueue.ts             # EXISTING: No changes needed
    useTaskProgress.ts          # EXISTING: No changes needed
  lib/
    upload/
      tusUpload.ts              # NEW: tus-js-client wrapper (non-React)
      uploadMetrics.ts          # NEW: Speed/ETA calculation utilities
      constants.ts              # NEW: Thresholds, chunk sizes, accepted types
    config.ts                   # EXISTING: May need TUS endpoint URL
  components/
    upload/
      FileProgress.tsx          # MODIFY: Add speed and ETA display
      FileQueueItem.tsx         # MINOR: Pass speed/ETA props down
```

### Pattern 1: File Size Routing in Orchestration Hook
**What:** Route files to direct upload or TUS based on size threshold
**When to use:** In `useUploadOrchestration.processFile()`, before upload begins
**Example:**
```typescript
// In useUploadOrchestration.ts
const SIZE_THRESHOLD = 80 * 1024 * 1024; // 80MB

const processFile = useCallback(async (item: FileQueueItem) => {
  if (item.file.size >= SIZE_THRESHOLD) {
    await processViaTus(item);
  } else {
    await processViaDirect(item);  // existing flow
  }
}, []);
```

### Pattern 2: TUS Upload with Metadata
**What:** Send file metadata (filename, language, model) through TUS Upload-Metadata header
**When to use:** Creating a new TUS upload
**Example:**
```typescript
// Source: https://github.com/tus/tus-js-client/blob/main/docs/api.md
import * as tus from 'tus-js-client';

const upload = new tus.Upload(file, {
  endpoint: '/uploads/files/',
  chunkSize: 50 * 1024 * 1024, // 50MB per prior decision
  retryDelays: [0, 1000, 3000, 5000],
  metadata: {
    filename: file.name,
    filetype: file.type,
    language: selectedLanguage,
    model: selectedModel,
  },
  onProgress: (bytesSent, bytesTotal) => {
    const percentage = Math.round((bytesSent / bytesTotal) * 100);
    // Update progress state
  },
  onSuccess: (payload) => {
    // Upload complete - extract TUS resource ID from upload.url
    // e.g., "/uploads/files/abc123" -> "abc123"
    const tusResourceId = upload.url?.split('/').pop();
    // Use this to retrieve backend task ID
  },
  onError: (error) => {
    // Handle upload error
  },
});

upload.start();
```

### Pattern 3: Speed and ETA Calculation with Smoothing
**What:** Calculate upload speed using exponential moving average to avoid jitter
**When to use:** In `onProgress` callback
**Example:**
```typescript
// uploadMetrics.ts
interface UploadMetrics {
  percentage: number;
  speedBytesPerSec: number;
  speedMBps: string;      // formatted "12.3 MB/s"
  etaSeconds: number;
  etaFormatted: string;   // formatted "2m 15s" or "< 1m"
}

class UploadSpeedTracker {
  private lastTime: number = 0;
  private lastBytes: number = 0;
  private smoothedSpeed: number = 0;
  private readonly alpha = 0.3; // EMA smoothing factor

  update(bytesSent: number, bytesTotal: number): UploadMetrics {
    const now = Date.now();
    const percentage = Math.round((bytesSent / bytesTotal) * 100);

    if (this.lastTime === 0) {
      this.lastTime = now;
      this.lastBytes = bytesSent;
      return { percentage, speedBytesPerSec: 0, speedMBps: '-- MB/s', etaSeconds: 0, etaFormatted: 'Calculating...' };
    }

    const elapsed = (now - this.lastTime) / 1000; // seconds
    if (elapsed < 0.5) {
      // Don't update too frequently
      return this.lastMetrics;
    }

    const bytesDelta = bytesSent - this.lastBytes;
    const instantSpeed = bytesDelta / elapsed;

    // Exponential moving average for smooth display
    this.smoothedSpeed = this.smoothedSpeed === 0
      ? instantSpeed
      : this.alpha * instantSpeed + (1 - this.alpha) * this.smoothedSpeed;

    const remaining = bytesTotal - bytesSent;
    const etaSeconds = this.smoothedSpeed > 0 ? remaining / this.smoothedSpeed : 0;

    this.lastTime = now;
    this.lastBytes = bytesSent;

    return {
      percentage,
      speedBytesPerSec: this.smoothedSpeed,
      speedMBps: `${(this.smoothedSpeed / (1024 * 1024)).toFixed(1)} MB/s`,
      etaSeconds,
      etaFormatted: formatEta(etaSeconds),
    };
  }

  reset(): void {
    this.lastTime = 0;
    this.lastBytes = 0;
    this.smoothedSpeed = 0;
  }
}
```

### Pattern 4: Task ID Retrieval After TUS Upload
**What:** Obtain the backend task ID after TUS upload completes for WebSocket subscription
**When to use:** In the `onSuccess` callback of the TUS upload

There are three viable approaches, ranked by implementation simplicity:

**Approach A: Poll by TUS resource ID (RECOMMENDED)**
The frontend sends the TUS resource UUID as metadata. After upload completes, poll a new endpoint that maps TUS resource ID to task ID. This requires a small backend addition.

```typescript
// Frontend: After TUS upload succeeds
onSuccess: async (payload) => {
  const tusResourceId = upload.url?.split('/').pop();
  // Poll until task is created (hook runs async)
  const taskId = await pollForTaskId(tusResourceId);
  // Now subscribe to WebSocket for transcription progress
}
```

**Approach B: Pre-generate task ID as metadata**
Frontend generates a UUID, sends it as TUS metadata. Backend uses this ID when creating the task. Frontend already knows the task ID before upload starts.

```typescript
// Frontend: Generate task ID before upload
const preGeneratedTaskId = crypto.randomUUID();
metadata: {
  filename: file.name,
  taskId: preGeneratedTaskId,  // Backend uses this as task UUID
}
// Frontend already knows the task ID -- subscribe to WebSocket immediately
```

**Approach C: Subscribe to WebSocket before knowing task ID**
Use a correlation mechanism where the frontend subscribes to a session-level WebSocket and the backend pushes the task ID once created.

**Recommendation:** Approach B is simplest -- the frontend generates the task ID and includes it in TUS metadata. The backend `UploadSessionService.start_transcription()` reads `metadata.get("taskId")` and uses it as the task UUID instead of generating one. This eliminates polling, extra endpoints, and timing issues. However, this requires a small backend change in `upload_session_service.py`.

### Anti-Patterns to Avoid
- **Setting chunkSize unnecessarily for direct uploads:** tus-js-client docs explicitly warn against setting chunkSize unless forced by server limits. For our TUS path, we ARE forced (Cloudflare 100MB limit), so 50MB is correct.
- **Creating a new Upload instance per chunk:** tus-js-client handles chunking internally. Create ONE Upload instance per file.
- **Using `onChunkComplete` for progress display:** Use `onProgress` for UI progress. `onChunkComplete` fires less frequently and represents server acknowledgment, not upload progress.
- **Showing raw speed without smoothing:** Instantaneous speed calculation fluctuates wildly. Always use exponential moving average.
- **Separate progress components for direct vs TUS:** Must be the same component. The routing decision is invisible to the user.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File chunking/splitting | Manual `File.slice()` + sequential upload | tus-js-client `chunkSize` option | TUS handles offset tracking, retry, resume |
| Upload resumability | Store byte offsets in localStorage | tus-js-client built-in fingerprinting | Protocol-level resume via HEAD request |
| Browser file type detection | Custom extension parsing | react-dropzone `accept` prop (existing) | Already handles MIME + extension validation |
| Upload retry with backoff | Custom retry loops | tus-js-client `retryDelays` option | Built-in exponential backoff with smart reset |

**Key insight:** tus-js-client does the heavy lifting. The frontend's job is (1) routing by size, (2) computing speed/ETA from raw bytes, and (3) unified progress display. Everything else is handled by the library.

## Common Pitfalls

### Pitfall 1: Task ID Not Available After TUS Upload
**What goes wrong:** TUS upload completes successfully but frontend cannot subscribe to WebSocket for transcription progress because it doesn't have a task ID.
**Why it happens:** TUS protocol returns `204 No Content` on final PATCH. The `upload_complete_dep` hook creates the task and returns an ID, but tuspyserver discards the return value. The response has no custom headers or body.
**How to avoid:** Use Approach B (pre-generated task ID in metadata). Frontend generates UUID, sends as TUS metadata `taskId`. Backend reads it and uses it when creating the domain task.
**Warning signs:** Upload progress reaches 100% but transcription never starts, or "waiting for task ID" state hangs.

### Pitfall 2: Vite Proxy Not Configured for /uploads/ Path
**What goes wrong:** TUS requests fail with 404 in development.
**Why it happens:** `vite.config.ts` proxy only covers `/speech-to-text`, `/tasks`, `/ws`, etc. The TUS endpoint at `/uploads/files/` is not proxied.
**How to avoid:** Add `/uploads` to the Vite proxy configuration.
**Warning signs:** TUS upload works in production (same origin) but fails in development.

### Pitfall 3: onProgress Not Firing for Small Chunks
**What goes wrong:** Progress bar jumps from 0% to 100% for files just above the 80MB threshold.
**Why it happens:** If chunkSize is large relative to file size, there may only be 1-2 chunks, so `onProgress` fires very few times.
**How to avoid:** For files near the threshold (80-150MB), the progress bar will naturally have fewer updates. This is acceptable -- the bar will still animate smoothly via CSS transitions on the Progress component. Consider using `uploadDataDuringCreation: true` to start uploading with the creation request.
**Warning signs:** Progress jumps from 0 to 50 to 100 instead of smooth progression.

### Pitfall 4: Speed Display Shows "0 MB/s" Initially
**What goes wrong:** Speed and ETA show meaningless values for the first 1-2 seconds.
**Why it happens:** Need at least two data points to calculate speed (delta bytes / delta time).
**How to avoid:** Show "Calculating..." or "--" for speed/ETA until at least 2 progress events have fired and 0.5+ seconds have elapsed.
**Warning signs:** "0 MB/s" or "Infinity" displayed briefly when upload starts.

### Pitfall 5: TUS Upload URL Relative vs Absolute
**What goes wrong:** tus-js-client fails to resume uploads because URL doesn't match.
**Why it happens:** The `Location` header returned by the backend contains a relative or absolute URL that may not match what the client expects when the Vite dev proxy is involved.
**How to avoid:** Set `removeFingerprintOnSuccess: true` to avoid stale resume attempts. In development, ensure the proxy preserves the `Location` header correctly. Resume functionality is Phase 9 scope, so for now, disable fingerprint storage with `storeFingerprintForResuming: false`.
**Warning signs:** Resumed uploads fail with 404, new uploads work fine.

### Pitfall 6: Direct Upload Progress Not Tracked
**What goes wrong:** The direct upload path (< 80MB) shows 0% then jumps to "processing" with no upload progress.
**Why it happens:** The existing `startTranscription()` uses `fetch()` which does not provide upload progress. `XMLHttpRequest` or `ReadableStream` would be needed.
**How to avoid:** For the direct path, show an indeterminate progress state during upload, then switch to determinate progress for transcription stages. Alternatively, use `XMLHttpRequest` with `upload.onprogress` for the direct path. The context says "Progress bar is identical for both direct and chunked uploads" -- this may require refactoring the direct upload to track progress too.
**Warning signs:** Direct uploads show no progress during upload phase, only during transcription.

## Code Examples

### tus-js-client Basic Integration
```typescript
// Source: https://github.com/tus/tus-js-client/blob/main/docs/api.md (verified v4)
import * as tus from 'tus-js-client';

function createTusUpload(
  file: File,
  endpoint: string,
  metadata: Record<string, string>,
  onProgress: (bytesSent: number, bytesTotal: number) => void,
  onSuccess: () => void,
  onError: (error: Error) => void,
): tus.Upload {
  const upload = new tus.Upload(file, {
    endpoint,
    chunkSize: 50 * 1024 * 1024,    // 50MB chunks
    retryDelays: [0, 1000, 3000, 5000],
    metadata,
    // Phase 8: Don't store fingerprints (resume is Phase 9)
    storeFingerprintForResuming: false,
    removeFingerprintOnSuccess: true,
    onProgress,
    onSuccess,
    onError,
  });

  return upload;
}

// Usage
const upload = createTusUpload(
  file,
  '/uploads/files/',
  { filename: file.name, filetype: file.type, language: 'en' },
  (sent, total) => console.log(`${Math.round(sent/total*100)}%`),
  () => console.log('Upload complete:', upload.url),
  (err) => console.error('Upload failed:', err),
);

upload.start();
```

### TypeScript Import Pattern
```typescript
// Source: https://github.com/tus/tus-js-client (v4, built-in types)
import * as tus from 'tus-js-client';

// Check browser support
if (!tus.isSupported) {
  console.warn('TUS not supported in this browser');
  // Fall back to direct upload for all files
}

// Access types
const upload: tus.Upload = new tus.Upload(file, options);
```

### Custom React Hook Pattern
```typescript
// hooks/useTusUpload.ts
import { useCallback, useRef, useState } from 'react';
import * as tus from 'tus-js-client';

interface TusUploadState {
  isUploading: boolean;
  percentage: number;
  speedMBps: string;
  etaFormatted: string;
  error: string | null;
  tusUrl: string | null;
}

function useTusUpload(endpoint: string) {
  const [state, setState] = useState<TusUploadState>({
    isUploading: false,
    percentage: 0,
    speedMBps: '-- MB/s',
    etaFormatted: 'Calculating...',
    error: null,
    tusUrl: null,
  });
  const uploadRef = useRef<tus.Upload | null>(null);

  const startUpload = useCallback((
    file: File,
    metadata: Record<string, string>,
    onComplete: (tusUrl: string) => void,
  ) => {
    const speedTracker = new UploadSpeedTracker();

    const upload = new tus.Upload(file, {
      endpoint,
      chunkSize: 50 * 1024 * 1024,
      retryDelays: [0, 1000, 3000, 5000],
      metadata,
      storeFingerprintForResuming: false,
      onProgress: (bytesSent, bytesTotal) => {
        const metrics = speedTracker.update(bytesSent, bytesTotal);
        setState(prev => ({
          ...prev,
          percentage: metrics.percentage,
          speedMBps: metrics.speedMBps,
          etaFormatted: metrics.etaFormatted,
        }));
      },
      onSuccess: () => {
        const tusUrl = upload.url || '';
        setState(prev => ({ ...prev, isUploading: false, percentage: 100, tusUrl }));
        onComplete(tusUrl);
      },
      onError: (error) => {
        setState(prev => ({
          ...prev,
          isUploading: false,
          error: error.message,
        }));
      },
    });

    uploadRef.current = upload;
    setState(prev => ({ ...prev, isUploading: true, error: null }));
    upload.start();
  }, [endpoint]);

  const abort = useCallback(() => {
    uploadRef.current?.abort(true);
    setState(prev => ({ ...prev, isUploading: false }));
  }, []);

  return { ...state, startUpload, abort };
}
```

### Vite Proxy Addition
```typescript
// vite.config.ts - add to proxy config
'/uploads': {
  target: apiUrl,
  changeOrigin: true,
},
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual File.slice() + sequential XHR | tus-js-client handles chunking | Always (TUS is the standard) | No manual chunk management |
| `use-tus` React wrapper | Direct tus-js-client v4 in custom hook | v4 release (2024) | Simpler, fewer dependencies, better TypeScript |
| `onChunkComplete` for UI | `onProgress` for UI, `onChunkComplete` for reliability | TUS FAQ clarification | Smoother progress updates |
| Separate upload UI for chunked | Unified progress regardless of path | Phase 8 decision | Better UX |

**Deprecated/outdated:**
- `@types/tus-js-client`: Not needed since v4 includes TypeScript types
- `use-tus` wrapper: Unclear v4 support, unnecessary abstraction for our use case
- tus-js-client v3.x: v4 only drops Node.js < 18 requirement, API is identical

## Open Questions

1. **Task ID handoff mechanism (CRITICAL)**
   - What we know: TUS `upload_complete_dep` hook return value is discarded by tuspyserver. The PATCH response is always `204 No Content` with no custom body. The `onSuccess` callback receives `lastResponse` which only has standard TUS headers.
   - What's unclear: Whether backend team prefers Approach B (pre-generated UUID in metadata) or a separate polling endpoint.
   - Recommendation: Approach B (pre-generated task ID in metadata) is simplest. Requires modifying `UploadSessionService.start_transcription()` to use `metadata.get("taskId")` instead of `str(uuid4())`. This is a ~3 line backend change. The frontend generates `crypto.randomUUID()` and includes it as TUS metadata.

2. **Direct upload progress tracking**
   - What we know: The existing direct upload uses `fetch()` which does NOT support upload progress tracking. The `fetch()` API has no `onprogress` equivalent for request bodies.
   - What's unclear: The context says "Progress bar is identical for both direct and chunked uploads -- same visual, same stats." This implies direct uploads also need speed/ETA.
   - Recommendation: For Phase 8, the direct upload path can show an indeterminate upload phase (spinner + "Uploading...") and then switch to determinate transcription progress. Making direct uploads show byte-level progress would require replacing `fetch()` with `XMLHttpRequest` which is a larger refactor. Alternatively, since files < 80MB upload quickly, the brief indeterminate phase is acceptable. Document this as a potential enhancement.

3. **Chunk size for TUS uploads**
   - What we know: Prior decision was 50MB. Cloudflare limit is 100MB per request body. tus-js-client docs warn "Do not set chunkSize unless forced."
   - What's unclear: Optimal chunk size for balance of progress granularity vs overhead.
   - Recommendation: Use 50MB. With a 200MB file, this gives 4 chunks = good progress granularity. The `onProgress` callback fires within each chunk too (not just between chunks), so progress is smooth regardless. The 50MB value provides safe margin below the 100MB Cloudflare limit.

4. **Browser support for TUS**
   - What we know: tus-js-client checks `XMLHttpRequest`, `Blob`, and `Blob.prototype.slice`. The `tus.isSupported` boolean can be checked at runtime.
   - What's unclear: Whether any target browsers lack support.
   - Recommendation: Check `tus.isSupported` and fall back to direct upload for all files if TUS is not supported. All modern browsers support TUS.

## Sources

### Primary (HIGH confidence)
- [tus-js-client API docs](https://github.com/tus/tus-js-client/blob/main/docs/api.md) - Complete v4 API reference, constructor options, callbacks
- [tus-js-client GitHub](https://github.com/tus/tus-js-client) - v4.3.1 latest, built-in TypeScript types
- [tuspyserver source code](file:.venv/Lib/site-packages/tuspyserver/routes/core.py) - Verified PATCH handler returns 204, discards hook return value (lines 276-284)
- [tuspyserver creation route](file:.venv/Lib/site-packages/tuspyserver/routes/creation.py) - POST returns 201 with Location header (line 354-367)

### Secondary (MEDIUM confidence)
- [tus-js-client FAQ](https://github.com/tus/tus-js-client/blob/main/docs/faq.md) - onProgress vs onChunkComplete difference
- [TUS protocol specification](https://tus.io/protocols/resumable-upload) - Protocol behavior reference
- [use-tus React wrapper](https://github.com/kqito/use-tus) - Evaluated and rejected for this project

### Tertiary (LOW confidence)
- WebSearch results for React + TUS integration patterns - Community patterns, not officially verified

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - tus-js-client is the official TUS client, v4.3.1 verified on npm, TypeScript types built-in
- Architecture: HIGH - Patterns derived from verified API docs and existing codebase analysis
- Pitfalls: HIGH - Task ID handoff verified by reading actual tuspyserver source code; Vite proxy gap identified from existing config
- Speed/ETA calculation: MEDIUM - Standard algorithm, no library-specific verification needed

**Research date:** 2026-01-29
**Valid until:** 2026-02-28 (30 days - stable libraries, well-documented patterns)
