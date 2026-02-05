# Phase 9: Resilience and Polish - Research

**Researched:** 2026-02-05
**Domain:** TUS upload retry, cancel, resume, and error handling in React/FastAPI stack
**Confidence:** HIGH

## Summary

This phase adds resilience features to the TUS chunked upload system built in Phases 7-8. The good news: tus-js-client v4.3.1 already has most of the infrastructure built in. Retry with exponential backoff is *already partially configured* (`retryDelays: [0, 1000, 3000, 5000]` in `constants.ts`). Cancel via `abort()` is *already wired* (the `useTusUpload` hook returns `{ abort: () => upload.abort(true) }` but nothing in the UI calls it). Resume after page refresh requires flipping `storeFingerprintForResuming` from `false` to `true` and adding a `findPreviousUploads()` flow. Error messaging requires classifying `DetailedError` objects by HTTP status and network condition.

The codebase was explicitly designed for this phase: `tusUpload.ts` line 41 comments `// Resume is Phase 9 scope -- disable fingerprint storage for now`. The `useTusUpload` hook already returns an `abort` function. The `FileQueueItem` type already has `errorMessage` and `technicalDetail` fields. The infrastructure is in place; this phase enables and wires it.

**Primary recommendation:** Enable tus-js-client's built-in URL storage for resume, add `onShouldRetry` for smart retry classification, wire the existing `abort` return value to a cancel button in the UI, and build an error classifier that maps `DetailedError` status codes to user-friendly messages.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **tus-js-client** | 4.3.1 (installed) | Retry, resume, cancel, error handling | Already installed. Built-in `retryDelays`, `findPreviousUploads()`, `abort()`, `DetailedError` with HTTP status |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **localStorage** (Web API) | Browser built-in | URL storage for resume | tus-js-client's `WebStorageUrlStorage` uses it automatically when `storeFingerprintForResuming: true` |
| **navigator.onLine** (Web API) | Browser built-in | Network status detection | tus-js-client checks this internally for retry decisions |
| **lucide-react** | Existing | Icons for cancel button, retry, error states | Already in project, used for `X`, `RotateCcw`, `AlertCircle` icons |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tus-js-client built-in retry | Custom retry wrapper | tus-js-client already handles retry correctly with counter reset on progress. No reason to replace it |
| tus-js-client localStorage storage | Custom localStorage wrapper | The built-in `WebStorageUrlStorage` handles all edge cases (Safari private mode, sandboxed iframes, malformed entries). Don't rebuild this |
| `onShouldRetry` callback | Default retry behavior | Default retries on non-4xx + 409 + 423. Adding `onShouldRetry` lets us skip retry on 413 (file too large) and 410 (expired upload) while retrying on 502/503 (proxy errors) |

**Installation:** No new dependencies needed. Everything is already installed.

## Architecture Patterns

### Current State (What Exists)

```
frontend/src/
  lib/upload/
    tusUpload.ts              # createTusUpload() - storeFingerprintForResuming: false (Phase 9 TODO)
    constants.ts              # TUS_RETRY_DELAYS = [0, 1000, 3000, 5000] (already configured)
    uploadMetrics.ts          # UploadSpeedTracker (no changes needed)
  hooks/
    useTusUpload.ts           # Returns { abort: () => upload.abort(true) } (unused by UI)
    useUploadOrchestration.ts # processViaTus() calls startTusUpload but ignores abort return
    useFileQueue.ts           # setFileError(id, message, technicalDetail) already exists
  components/upload/
    FileQueueItem.tsx         # Has error display + retry button. No cancel button during upload
    FileProgress.tsx          # Progress bar with speed/ETA. No cancel affordance
```

### Target State (What Phase 9 Adds)

```
frontend/src/
  lib/upload/
    tusUpload.ts              # MODIFY: storeFingerprintForResuming: true, add onShouldRetry
    tusErrorClassifier.ts     # NEW: Map DetailedError to user-friendly messages
    constants.ts              # MODIFY: Update TUS_RETRY_DELAYS for true exponential backoff
  hooks/
    useTusUpload.ts           # MODIFY: Add findPreviousUploads/resume flow, expose abort ref
    useUploadOrchestration.ts # MODIFY: Store abort ref, wire cancel, handle resume on mount
    useFileQueue.ts           # NO CHANGE (error infrastructure already exists)
  components/upload/
    FileQueueItem.tsx         # MODIFY: Add cancel button during uploading state
    FileProgress.tsx          # MODIFY: Add "Retrying..." indicator, cancel button slot
```

### Pattern 1: Enable Resume via Built-in URL Storage
**What:** Flip `storeFingerprintForResuming` to `true` and add `findPreviousUploads()` flow
**When to use:** In `tusUpload.ts` and `useTusUpload.ts`
**Why it works:** tus-js-client generates a fingerprint from `[name, type, size, lastModified, endpoint]` and stores the TUS upload URL in localStorage under `tus::{fingerprint}::{random-id}`. On page refresh, the same file produces the same fingerprint, enabling URL lookup. The server-side HEAD request then returns the current offset, and upload resumes from there.

```typescript
// Source: tus-js-client v4.3.1 lib/browser/fileSignature.js (verified in node_modules)
// Fingerprint = ['tus-br', file.name, file.type, file.size, file.lastModified, options.endpoint].join('-')

// In tusUpload.ts - enable storage
const upload = new tus.Upload(file, {
  endpoint: TUS_ENDPOINT,
  chunkSize: TUS_CHUNK_SIZE,
  retryDelays: TUS_RETRY_DELAYS,
  metadata,
  storeFingerprintForResuming: true,   // CHANGED from false
  removeFingerprintOnSuccess: true,    // Clean up after success (unchanged)
  // ... callbacks
});

// In useTusUpload.ts - resume flow
const upload = createTusUpload(file, metadata, callbacks);

const previousUploads = await upload.findPreviousUploads();
if (previousUploads.length > 0) {
  // Resume the most recent upload
  upload.resumeFromPreviousUpload(previousUploads[0]);
}
upload.start();
```

**Key detail from source code:** The `findPreviousUploads()` method (upload.js line 160-163) calls `this._urlStorage.findUploadsByFingerprint(fingerprint)` which searches localStorage for keys matching `tus::{fingerprint}::`. The `resumeFromPreviousUpload()` method (line 166-169) sets `this.url` to the stored upload URL. When `start()` is called, it sends a HEAD request to that URL to get the current offset, then resumes from there.

**Key detail from server:** tuspyserver's HEAD handler (core.py line 55-179) returns `Upload-Offset` with the current byte offset. If the upload expired, it returns `410 Gone`. If the file doesn't exist, it returns `404 Not Found`. tus-js-client handles both: on 4xx, it removes the stored fingerprint and creates a new upload from scratch.

### Pattern 2: Cancel via abort() with Server Termination
**What:** Wire the existing `abort(true)` call to a UI cancel button
**When to use:** When user clicks cancel during upload
**How abort(true) works (verified in source):**

```typescript
// Source: tus-js-client v4.3.1 lib/upload.js lines 456-486
// abort(shouldTerminate = true):
//   1. Stops parallel uploads if any
//   2. Aborts current XMLHttpRequest
//   3. Sets _aborted = true (suppresses future error emissions)
//   4. Clears retry timeout
//   5. If shouldTerminate AND url exists:
//      - Sends DELETE to server URL (tuspyserver termination extension)
//      - Removes entry from URL storage (localStorage cleanup)

// In useUploadOrchestration.ts:
const abortRef = useRef<(() => void) | null>(null);

// During processViaTus:
const { abort } = startTusUpload(item.file, metadata, callbacks);
abortRef.current = abort;

// Cancel handler:
const handleCancel = useCallback((id: string) => {
  if (abortRef.current) {
    abortRef.current();  // calls upload.abort(true) -> DELETE + localStorage cleanup
    abortRef.current = null;
  }
  updateFileStatus(id, 'pending');  // Reset to pending so user can retry
}, [updateFileStatus]);
```

**Important:** `abort(true)` returns a Promise (for the DELETE request). The `_aborted = true` flag ensures no `onError` callback fires after abort, so the UI won't show a spurious error message.

### Pattern 3: Smart Retry with onShouldRetry
**What:** Add `onShouldRetry` callback to classify errors and decide whether to retry
**When to use:** In `tusUpload.ts` configuration
**How default retry works (verified in source, upload.js lines 1050-1081):**

```typescript
// Default behavior (without onShouldRetry):
// Retries if ALL are true:
//   1. retryDelays is not null
//   2. retryAttempt < retryDelays.length
//   3. err.originalRequest is not null (i.e., it's an HTTP error, not a setup error)
//   4. defaultOnShouldRetry(err) returns true:
//      - Status is NOT in 400 range, OR status is 409 or 423
//      - navigator.onLine is true (or not available)
//
// CRITICAL: Retry counter resets to 0 when progress is made (upload.js line 501-503)
// This means: if a 500MB file has a network blip every 100MB, it will retry
// indefinitely (counter resets after each successful chunk transfer)

// Custom onShouldRetry for this project:
onShouldRetry: (err: DetailedError, retryAttempt: number, options: UploadOptions) => {
  const status = err.originalResponse ? err.originalResponse.getStatus() : 0;

  // Never retry these - they won't succeed on retry:
  if (status === 413) return false;  // File too large (server-side limit)
  if (status === 415) return false;  // Unsupported media type
  if (status === 410) return false;  // Upload expired (gone)
  if (status === 403) return false;  // Forbidden

  // Always retry these - they're transient:
  if (status === 0) return true;     // Network error (no response)
  if (status === 408) return true;   // Request timeout
  if (status === 429) return true;   // Rate limited
  if (status === 502) return true;   // Bad gateway (Cloudflare)
  if (status === 503) return true;   // Service unavailable
  if (status === 504) return true;   // Gateway timeout

  // Default behavior for everything else:
  return (!inStatusCategory(status, 400) || status === 409 || status === 423);
}
```

### Pattern 4: Error Classification for User-Friendly Messages
**What:** Map `DetailedError` properties to actionable user-facing messages
**When to use:** In `onError` callback, after all retries exhausted
**Source data structure (verified, error.js lines 1-25):**

```typescript
// tus-js-client DetailedError structure:
// - message: string (e.g., "tus: unexpected response while creating upload")
// - originalRequest: HttpRequest | null
// - originalResponse: HttpResponse | null  (has getStatus(), getBody(), getHeader())
// - causingError: Error | null

// Error classifier:
interface ClassifiedError {
  userMessage: string;       // What the user sees
  technicalDetail: string;   // What "Show details" reveals
  isRetryable: boolean;      // Whether manual retry makes sense
}

function classifyTusError(error: Error): ClassifiedError {
  // Check if it's a DetailedError with HTTP context
  const detailedError = error as any;
  const status = detailedError.originalResponse?.getStatus?.() ?? 0;
  const body = detailedError.originalResponse?.getBody?.() ?? '';

  // Network errors (no response at all)
  if (status === 0) {
    return {
      userMessage: 'Network connection lost. Check your internet and try again.',
      technicalDetail: `Network error: ${error.message}`,
      isRetryable: true,
    };
  }

  // Server-side file issues
  if (status === 413) {
    return {
      userMessage: 'File is too large for the server. Maximum size is 5GB.',
      technicalDetail: `HTTP 413: ${body}`,
      isRetryable: false,
    };
  }

  if (status === 410) {
    return {
      userMessage: 'Upload session expired. Please start the upload again.',
      technicalDetail: `HTTP 410 Gone: ${body}`,
      isRetryable: true,  // Retry will create a new upload
    };
  }

  // Proxy/infrastructure errors
  if (status === 502 || status === 503 || status === 504) {
    return {
      userMessage: 'Server is temporarily unavailable. Please try again in a moment.',
      technicalDetail: `HTTP ${status}: ${body}`,
      isRetryable: true,
    };
  }

  // Cloudflare-specific
  if (status === 520 || status === 521 || status === 522 || status === 523 || status === 524) {
    return {
      userMessage: 'Server connection issue (Cloudflare). Please try again.',
      technicalDetail: `Cloudflare HTTP ${status}: ${body}`,
      isRetryable: true,
    };
  }

  // Permission errors
  if (status === 403) {
    return {
      userMessage: 'Upload not permitted. The server rejected this file.',
      technicalDetail: `HTTP 403 Forbidden: ${body}`,
      isRetryable: false,
    };
  }

  // Generic fallback
  return {
    userMessage: 'Upload failed after multiple attempts. Please try again.',
    technicalDetail: error.message,
    isRetryable: true,
  };
}
```

### Pattern 5: Retry Delays for True Exponential Backoff
**What:** Update `TUS_RETRY_DELAYS` to match RESIL-01 requirement (3 attempts with exponential backoff)
**Current value:** `[0, 1000, 3000, 5000]` (4 retries, linear-ish)
**Requirement:** "3 attempts with exponential backoff"

```typescript
// RESIL-01 specifies 3 retry attempts with exponential backoff
// Exponential backoff: base * 2^attempt
// Base = 1000ms: [1000, 2000, 4000]
// With jitter to prevent thundering herd:
export const TUS_RETRY_DELAYS = [1000, 2000, 4000];

// Note: The array length IS the max retry count.
// 3 elements = 3 retries (4 total attempts including initial)
// tus-js-client resets the counter on progress (upload.js line 501-503),
// so long uploads can survive more than 3 total blips as long as
// some data transfers between each failure.
```

### Anti-Patterns to Avoid
- **Building custom retry logic around tus-js-client:** The library already has retry built in. Don't wrap `start()` in a retry loop; use `retryDelays` and `onShouldRetry`.
- **Storing upload state in React state for resume:** The `File` object is lost on page refresh. Resume requires the user to re-select the same file. tus-js-client matches by fingerprint (name + type + size + lastModified), not by reference.
- **Calling abort(false) for cancel:** `abort(false)` pauses but leaves the server resource alive and localStorage entry intact. For user-initiated cancel, use `abort(true)` to clean up both server and client state.
- **Showing "Upload Failed" without context:** The `DetailedError` contains HTTP status, response body, and request details. Always classify the error and show an actionable message.
- **Resetting file status to 'error' on abort:** When the user cancels, the `_aborted` flag suppresses `onError`. Don't set error state in the cancel handler; set it back to 'pending' for re-upload.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with backoff | Custom setTimeout loops | tus-js-client `retryDelays` + `onShouldRetry` | Library handles counter reset on progress, navigator.onLine check, abort integration |
| Upload URL persistence | Custom localStorage read/write | tus-js-client `storeFingerprintForResuming: true` | Built-in `WebStorageUrlStorage` handles Safari private mode, sandboxed iframes, malformed entries, key prefix scoping |
| Fingerprint generation | Custom file hashing | tus-js-client default fingerprint | Uses name+type+size+lastModified+endpoint. Fast (no file content read), unique enough for practical purposes |
| Server-side resume offset | Custom offset tracking API | TUS HEAD request (built into protocol) | tuspyserver returns `Upload-Offset` header. tus-js-client sends HEAD automatically on resume |
| Upload termination on cancel | Custom DELETE endpoint | tus-js-client `abort(true)` | Sends DELETE per TUS termination extension, cleans up localStorage |

**Key insight:** tus-js-client v4 already implements RESIL-01 through RESIL-04 at the protocol level. This phase's work is primarily *configuration and UI wiring*, not building new infrastructure.

## Common Pitfalls

### Pitfall 1: File Object Lost on Page Refresh
**What goes wrong:** User refreshes page, the `File` reference is gone. tus-js-client needs a `File` to compute the fingerprint and provide data for resumed chunks.
**Why it happens:** JavaScript `File` objects exist only in memory. They are not serializable or persistable.
**How to avoid:** Resume requires the user to **re-select the same file**. The UI must prompt: "You have an interrupted upload for [filename]. Select the file again to resume." The fingerprint (`name+type+size+lastModified`) will match the stored URL. tus-js-client then sends a HEAD to get the offset and resumes from there.
**Warning signs:** Code tries to "auto-resume" without a file reference, or stores file content in localStorage (which would be enormous and impractical).

### Pitfall 2: Stale Resume URLs After Server Restart
**What goes wrong:** tus-js-client finds a previous upload URL in localStorage, sends HEAD, gets 404 because the server was restarted and TUS files were cleaned up.
**Why it happens:** tuspyserver stores TUS files on disk in `UPLOAD_DIR/tus/`. Server restart + cleanup = files gone. But localStorage still has the URL.
**How to avoid:** tus-js-client already handles this correctly. From source (upload.js lines 676-683): on 4xx response to HEAD, it removes the fingerprint from URL storage and falls back to creating a new upload if an `endpoint` is provided. No special handling needed.
**Warning signs:** Only an issue if `endpoint` is not set (but we always set it).

### Pitfall 3: Upload Expiry vs Resume Window
**What goes wrong:** User pauses upload, comes back the next day, file data is partially on server but the TUS upload has expired (1 day TTL per `days_to_keep=1`).
**Why it happens:** tuspyserver sets `expires` on creation, and the core.py PATCH handler checks `_check_upload_expired()`. HEAD returns 410 Gone for expired uploads.
**How to avoid:** tus-js-client handles 410 as a 4xx (removes stored URL, creates new upload). The user experience: "Your previous upload expired. Starting fresh." This is acceptable behavior. If longer resume windows are needed, increase `days_to_keep` in `tus_upload_api.py`.
**Warning signs:** Users complain that overnight uploads need to restart from scratch. Consider increasing `days_to_keep` to 3.

### Pitfall 4: Cancel During Retry Timeout
**What goes wrong:** Upload fails, retry is scheduled (setTimeout), user clicks cancel but upload restarts after the timeout.
**Why it happens:** `abort()` might not clear the retry timeout if called incorrectly.
**How to avoid:** From source (upload.js lines 472-474): `abort()` explicitly clears `this._retryTimeout` with `clearTimeout()`. This is already handled. Just ensure the UI calls the abort function that wraps `upload.abort(true)`.
**Warning signs:** Upload appears to cancel but then restarts a few seconds later.

### Pitfall 5: Multiple Resume Candidates
**What goes wrong:** `findPreviousUploads()` returns multiple entries for the same file (e.g., user started upload, cancelled, started again).
**Why it happens:** Each `createTusUpload()` call stores a new entry in localStorage with a random ID suffix. If the user cancels with `abort(true)`, the entry is cleaned up. But if the page crashes or the user navigates away without cancelling, the entry persists.
**How to avoid:** Always use `previousUploads[0]` (most recent). `removeFingerprintOnSuccess: true` cleans up after successful uploads. Consider periodic cleanup of stale entries.
**Warning signs:** Multiple stale `tus::` entries accumulating in localStorage.

### Pitfall 6: Retrying UI Indicator Missing
**What goes wrong:** Network blip causes retry, but user sees the progress bar frozen with no indication that anything is happening. User thinks upload is stuck and cancels.
**Why it happens:** During retry delay (1-4 seconds), no callbacks fire. The UI shows stale progress with no visual change.
**How to avoid:** Use `onShouldRetry` to detect when a retry is about to happen and show a "Retrying..." indicator. Alternatively, use `onBeforeRequest` / `onAfterResponse` hooks to detect retry starts.
**Warning signs:** Users cancel uploads that would have recovered automatically.

## Code Examples

### Complete Resume Flow (Verified from tus-js-client source)
```typescript
// Source: tus-js-client v4.3.1 upload.js lines 160-169, browser/urlStorage.js, browser/fileSignature.js

import * as tus from 'tus-js-client';

export async function createResumableTusUpload(
  file: File,
  metadata: Record<string, string>,
  callbacks: TusUploadCallbacks,
): Promise<tus.Upload> {
  const upload = new tus.Upload(file, {
    endpoint: TUS_ENDPOINT,
    chunkSize: TUS_CHUNK_SIZE,
    retryDelays: TUS_RETRY_DELAYS,
    metadata,
    storeFingerprintForResuming: true,
    removeFingerprintOnSuccess: true,
    onProgress: callbacks.onProgress,
    onSuccess: () => callbacks.onSuccess(upload.url ?? ''),
    onError: (error) => callbacks.onError(
      error instanceof Error ? error : new Error(String(error))
    ),
    onShouldRetry: (err, retryAttempt, options) => {
      const status = err.originalResponse ? err.originalResponse.getStatus() : 0;
      // Don't retry permanent failures
      if (status === 413 || status === 415 || status === 410 || status === 403) return false;
      // Retry transient failures
      if (status === 0 || status === 408 || status === 429) return true;
      if (status >= 500) return true;
      // Default behavior for other cases
      const inRange = (s: number, category: number) => s >= category && s < category + 100;
      return (!inRange(status, 400) || status === 409 || status === 423);
    },
  });

  // Check for previous uploads to resume
  const previousUploads = await upload.findPreviousUploads();
  if (previousUploads.length > 0) {
    upload.resumeFromPreviousUpload(previousUploads[0]);
  }

  return upload;
}
```

### Cancel Button Integration
```typescript
// In useUploadOrchestration.ts
const abortControllerRef = useRef<Map<string, () => void>>(new Map());

const handleCancel = useCallback((fileId: string) => {
  const abort = abortControllerRef.current.get(fileId);
  if (abort) {
    abort();  // upload.abort(true) -> DELETE + localStorage cleanup
    abortControllerRef.current.delete(fileId);
  }
  // Reset file back to pending (not error)
  updateFileStatus(fileId, 'pending');
  // Clear progress
  updateFileProgress(fileId, 0, 'uploading');
  // Clear current processing ref if this was the active file
  if (currentFileIdRef.current === fileId) {
    currentFileIdRef.current = null;
    currentTaskIdRef.current = null;
  }
}, [updateFileStatus, updateFileProgress]);

// In processViaTus, store the abort function:
const { abort } = startTusUpload(item.file, metadata, callbacks);
abortControllerRef.current.set(item.id, abort);
```

### Error Classifier Module
```typescript
// lib/upload/tusErrorClassifier.ts
import type { DetailedError } from 'tus-js-client';

export interface ClassifiedUploadError {
  userMessage: string;
  technicalDetail: string;
  isRetryable: boolean;
}

export function classifyUploadError(error: Error): ClassifiedUploadError {
  const detailed = error as DetailedError;
  const status = detailed.originalResponse?.getStatus?.() ?? 0;
  const body = detailed.originalResponse?.getBody?.() ?? '';

  if (status === 0 || !detailed.originalResponse) {
    return {
      userMessage: 'Network connection lost. Check your internet and try again.',
      technicalDetail: error.message,
      isRetryable: true,
    };
  }

  const classificationMap: Record<number, ClassifiedUploadError> = {
    413: {
      userMessage: 'File exceeds the maximum upload size (5GB).',
      technicalDetail: `HTTP 413: ${body}`,
      isRetryable: false,
    },
    410: {
      userMessage: 'Upload session expired. Please start the upload again.',
      technicalDetail: `HTTP 410: ${body}`,
      isRetryable: true,
    },
    403: {
      userMessage: 'Upload not permitted. The server rejected this request.',
      technicalDetail: `HTTP 403: ${body}`,
      isRetryable: false,
    },
    415: {
      userMessage: 'File type not supported by the server.',
      technicalDetail: `HTTP 415: ${body}`,
      isRetryable: false,
    },
  };

  if (classificationMap[status]) return classificationMap[status];

  if (status >= 500) {
    return {
      userMessage: 'Server error occurred. Please try again in a moment.',
      technicalDetail: `HTTP ${status}: ${body}`,
      isRetryable: true,
    };
  }

  return {
    userMessage: 'Upload failed. Please try again.',
    technicalDetail: error.message,
    isRetryable: true,
  };
}
```

### Resume Prompt UI Pattern
```typescript
// When user drops a file, check for previous uploads:
const checkForResumableUpload = async (file: File): Promise<boolean> => {
  // Create a temporary upload instance just for fingerprint lookup
  const tempUpload = new tus.Upload(file, {
    endpoint: TUS_ENDPOINT,
    storeFingerprintForResuming: true,
  });
  const previous = await tempUpload.findPreviousUploads();
  return previous.length > 0;
};

// UI: "Resume interrupted upload?" or silently resume (recommended for simplicity)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom retry loops with setTimeout | tus-js-client `retryDelays` + `onShouldRetry` | Always (TUS standard) | No custom retry code needed |
| Manual localStorage for upload state | tus-js-client `storeFingerprintForResuming` | tus-js-client v2+ (2020) | Fingerprint-based URL storage with built-in edge case handling |
| `upload.abort()` without termination | `upload.abort(true)` for server+client cleanup | tus-js-client v2+ | Clean cancellation with TUS termination extension |
| Generic "Upload Failed" errors | `DetailedError` with HTTP status/body | tus-js-client v2+ | Error classification enables actionable messages |

**Deprecated/outdated:**
- tus-js-client `resume` option: Removed in v2. Use `findPreviousUploads()` + `resumeFromPreviousUpload()` instead
- Manual `XMLHttpRequest.upload.onprogress` for retry indicator: tus-js-client handles progress internally

## Open Questions

1. **Resume UX: Silent vs. Prompted**
   - What we know: When user re-selects a file after page refresh, `findPreviousUploads()` will find the stored URL. The upload can resume automatically or the user can be prompted.
   - What's unclear: Whether users should be asked "Resume from X%?" or it should just happen.
   - Recommendation: **Silent resume** for simplicity. When a file is added to the queue and upload begins, check for previous uploads and resume automatically. The progress bar will jump to the resumed offset. If resume fails (404/410), silently restart from scratch. No user prompt needed.

2. **Cancel button placement**
   - What we know: `FileQueueItem.tsx` currently shows action buttons (Play, Retry, Remove) based on status. During `uploading` state, no cancel button exists.
   - What's unclear: Whether cancel should be a button in the file row or a global "Cancel All" button.
   - Recommendation: Per-file cancel button in the same action area. The `X` button is already used for remove (pending only). During uploading, show a dedicated cancel/stop button (e.g., Square icon for stop).

3. **Retry indicator in progress bar**
   - What we know: During retry delay (1-4 seconds), no callbacks fire from tus-js-client. The UI is frozen.
   - What's unclear: Best way to detect "currently retrying" state without internal tus-js-client state access.
   - Recommendation: Use the `onShouldRetry` callback as a signal. When it returns `true`, emit a callback to the UI before returning. This adds a brief "Retrying..." overlay on the progress bar. When `onProgress` fires again, clear the indicator. Alternatively, track time since last progress update and show "Retrying..." if > 2 seconds with no progress.

4. **localStorage cleanup for abandoned uploads**
   - What we know: `abort(true)` cleans up. `removeFingerprintOnSuccess: true` cleans up on success. But page crashes, browser kills, etc. can leave orphaned entries.
   - What's unclear: Whether orphaned `tus::` entries in localStorage accumulate over time.
   - Recommendation: For now, rely on the built-in cleanup (`removeFingerprintOnSuccess: true` + `abort(true)`). If stale entries become a problem, add a cleanup utility that removes entries older than 3 days. This is low priority.

## Sources

### Primary (HIGH confidence)
- [tus-js-client source: upload.js](file:frontend/node_modules/tus-js-client/lib/upload.js) - Verified retry logic (lines 1050-1081), abort (lines 456-486), error emission (lines 492-523), URL storage save/remove (lines 897-946)
- [tus-js-client source: error.js](file:frontend/node_modules/tus-js-client/lib/error.js) - DetailedError class with originalRequest, originalResponse, causingError
- [tus-js-client source: browser/urlStorage.js](file:frontend/node_modules/tus-js-client/lib/browser/urlStorage.js) - WebStorageUrlStorage using localStorage with `tus::` prefix
- [tus-js-client source: browser/fileSignature.js](file:frontend/node_modules/tus-js-client/lib/browser/fileSignature.js) - Fingerprint = name+type+size+lastModified+endpoint
- [tus-js-client source: index.d.ts](file:frontend/node_modules/tus-js-client/lib/index.d.ts) - TypeScript types for Upload, PreviousUpload, DetailedError, UrlStorage
- [tuspyserver source: core.py](file:.venv/Lib/site-packages/tuspyserver/routes/core.py) - HEAD returns Upload-Offset (line 154), 410 for expired (line 94), 404 for missing (line 90)
- [tus-js-client API docs](https://github.com/tus/tus-js-client/blob/main/docs/api.md) - Complete v4 options reference
- [tus-js-client FAQ](https://github.com/tus/tus-js-client/blob/main/docs/faq.md) - Retry behavior, counter reset on progress

### Secondary (MEDIUM confidence)
- [tus-js-client usage docs](https://github.com/tus/tus-js-client/blob/main/docs/usage.md) - Resume flow example with findPreviousUploads
- [tus-js-client npm](https://www.npmjs.com/package/tus-js-client/v/4.3.1) - Version confirmation

### Tertiary (LOW confidence)
- WebSearch: UX error message patterns - General best practices, not TUS-specific

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All features are built into tus-js-client v4.3.1 already installed. Verified by reading source code in node_modules.
- Architecture: HIGH - Patterns derived from actual source code analysis of retry, abort, URL storage, and error handling in upload.js. Server-side behavior verified in tuspyserver core.py.
- Pitfalls: HIGH - Each pitfall verified against source code behavior. File-loss-on-refresh is a fundamental browser limitation. Retry counter reset is explicitly coded (upload.js line 501-503).
- Error classification: MEDIUM - HTTP status codes are standard, but exact server responses from tuspyserver under various failure modes would benefit from integration testing.

**Research date:** 2026-02-05
**Valid until:** 2026-03-07 (30 days - stable library, well-understood patterns)
