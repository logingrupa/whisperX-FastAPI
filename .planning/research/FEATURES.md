# Feature Landscape: Chunked File Uploads

**Domain:** Large file upload UX for audio/video transcription
**Researched:** 2026-01-29
**Confidence:** HIGH (verified across multiple authoritative sources)

## Context

WhisperX transcription app with 500MB+ audio/video files. Need chunked uploads to work through Cloudflare's 100MB limit. Users currently have:
- Drag-and-drop with react-dropzone
- Multi-file queue with processing
- Real-time WebSocket progress (for transcription stages)
- File format validation (magic bytes)

---

## Table Stakes (Must Have)

Features users expect for chunked uploads to feel complete. Missing any = upload feels broken.

| Feature | Why Expected | Complexity | Testable Criteria |
|---------|--------------|------------|-------------------|
| **Overall file progress bar** | Users need to know upload status at a glance; transparent progress reduces anxiety | Low | Progress bar shows 0-100% for entire file, updates smoothly during upload |
| **Smooth progress updates** | Chunked uploads can appear "jumpy" with large chunks; users expect linear progress | Low | Progress bar updates at least every 2-3 seconds for 500MB file |
| **Automatic retry on failure** | Network hiccups are common; users expect system to handle them silently | Medium | Failed chunk retries automatically (max 3 attempts) before showing error |
| **Clear error messages** | "Upload Failed" is useless; users need actionable information | Low | Error shows what happened + what to do: "Network error. Click to retry." |
| **Cancel upload button** | Users must be able to stop an upload in progress | Low | Cancel button visible during upload; click stops upload immediately |
| **Resume after page refresh** | Users accidentally close tabs; losing 80% of a 500MB upload is unacceptable | High | Upload resumes from last successful chunk after page reload |
| **Upload speed indicator** | For large files, users want to estimate when upload will complete | Low | Shows "X MB/s" or "~Y minutes remaining" |
| **File size validation before upload** | Prevent wasted time on files that will fail server-side limits | Low | Files over limit show error immediately, not after partial upload |

### Why These Are Table Stakes

Research consistently shows:
- "Transparent progress reduces anxiety and improves the experience" - users abandon unclear uploads
- "In the event of a network failure, continue uploading from the point of interruption instead of starting over" - modern expectation
- "Provide informative error messages that help users correct mistakes" - vague errors cause support tickets

---

## Differentiators (Nice to Have)

Features that enhance experience but aren't required for v1.1. Consider for v1.2+.

| Feature | Value Proposition | Complexity | When to Build |
|---------|-------------------|------------|---------------|
| **Pause/resume button** | User-initiated pause for bandwidth management | Medium | When users report needing to pause for other activities |
| **Per-chunk progress visualization** | Advanced users see granular upload detail | Medium | When debugging/transparency is requested |
| **Background upload via Service Worker** | Upload continues if user navigates away from page | High | When users report losing uploads from navigation |
| **Parallel chunk uploads** | Faster uploads on high-bandwidth connections | Medium | When upload speed is bottleneck for power users |
| **Upload queue prioritization** | Drag to reorder which files upload first | Low | When users report needing to change order mid-batch |
| **Upload bandwidth throttling** | Let users limit upload speed to preserve other network activity | Medium | When users report network congestion issues |
| **Offline queue with auto-resume** | Queue files while offline, upload when connection returns | High | When mobile/unstable network users are significant |
| **Pre-upload compression** | Client-side audio/video compression before upload | High | Only if transcription quality is unaffected |

### Differentiation Notes

- **Pause/resume** is highly valued: "Pause and resume functions give users control over their uploads"
- **Background upload** is a power feature: "Service workers allow uploads to continue in the background, even if users navigate away"
- **Parallel uploads** improve speed but add complexity: "Parallel uploading increases network utilization and improves upload speed"

---

## Anti-Features (Don't Build for v1.1)

Features to explicitly exclude. Common mistakes or scope creep.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Confirmation dialog on cancel** | Adds friction; cancel should be immediate + recoverable | Let users cancel instantly; file stays in queue for re-upload |
| **Per-chunk error handling UI** | Overwhelming for users; they don't care which chunk failed | Show single "Upload failed" with retry; handle chunk logic internally |
| **Chunk size configuration** | Users don't understand chunks; this is implementation detail | Auto-select optimal chunk size (5MB) based on testing |
| **Upload history/persistence across sessions** | Scope creep; v1.1 is about working uploads, not upload management | Clear queue on session end; consider for v2 |
| **Detailed upload analytics** | Nice for devs, confusing for users | Log internally; don't expose in UI |
| **Multiple simultaneous file uploads** | Current architecture is sequential; adds complexity | Keep sequential processing; mark as future enhancement |
| **Auto-resume after days** | TUS supports this, but adds state management complexity | Resume works within session; after 24h, require re-upload |
| **Upload to multiple destinations** | Out of scope; we only need local server storage | Single destination; add if needed later |

### Anti-Feature Rationale

- **Confirmation dialogs:** "To balance safety and usability, optimally use confirmation dialogs only for required actions" - cancel is easily reversible
- **Chunk configuration:** "The optimal chunk size depends on network conditions and browser limitations" - this is our problem, not user's
- **Over-engineering resume:** "Returning an error in a timely manner and letting the user retry is a good UX practice" - don't over-promise

---

## UX Patterns

### What Users Expect to See During Large Uploads

**Visual State Progression:**
1. File added -> File card with name, size, thumbnail (if applicable)
2. Upload starts -> Progress bar appears, "Uploading..." status
3. During upload -> Progress bar fills, speed indicator updates, time remaining shown
4. Chunk fails (hidden) -> Auto-retry happens silently
5. All retries fail -> Error state with "Retry" button and clear message
6. Upload complete -> Checkmark, "Processing..." begins (existing WebSocket flow)

**Progress Bar Behavior:**
- Single progress bar per file (not per chunk)
- Smooth animation between chunk completions
- For 500MB file with 5MB chunks: updates every ~2-3 seconds on typical connection
- Never regresses (goes backwards) - confuses users

**Error Handling Hierarchy:**
1. **Transient errors (network hiccup):** Retry silently with exponential backoff (1s, 2s, 4s)
2. **Recoverable errors (server busy):** Retry with backoff, show "Retrying..." after 3rd attempt
3. **Permanent errors (file too large, auth failed):** Stop immediately, show actionable error
4. **User-initiated cancel:** Stop upload, keep file in queue as "Ready"

**Cancel Behavior:**
- Button appears immediately when upload starts
- Click cancels current upload, no confirmation needed
- File remains in queue with "Ready" status for re-upload
- In-flight chunks are aborted (not completed then discarded)

**Resume Behavior:**
- On page refresh during upload: detect incomplete upload in localStorage
- Show prompt: "Resume upload of filename.mp4? (450MB remaining)" with Resume/Start Over buttons
- Resume continues from last confirmed chunk
- Start Over clears saved state, begins fresh

**Retry Behavior:**
- Automatic retry: 3 attempts with exponential backoff (1s, 2s, 4s) + jitter
- After 3 failures: show error state with manual "Retry" button
- Manual retry: clears error, restarts from last successful chunk
- "Retrying in X seconds..." message only shown after first visible failure

### Multi-File Queue Behavior

Current behavior (keep):
- Sequential file processing (one at a time)
- Queue shows all files with individual status
- "Start All" processes queue in order

Chunked upload additions:
- Each file shows its own progress bar during upload
- Other files in queue show "Queued" status
- Failed files don't block queue (skip to next, user can retry later)

---

## Feature Dependencies

```
File Size Validation (pre-upload)
    |
    v
Chunked Upload Core (slicing + XHR)
    |
    +---> Progress Tracking (per-chunk -> aggregate)
    |
    +---> Auto-Retry Logic (per-chunk)
    |
    v
Cancel Handling (abort XHR)
    |
    v
Resume Logic (localStorage state)
    |
    v
[Existing] WebSocket Progress (transcription stages)
```

**Build Order Implications:**
1. Core chunking + progress (table stakes, must work)
2. Auto-retry (table stakes, prevents user frustration)
3. Cancel (table stakes, user control)
4. Resume (table stakes, prevents lost uploads)
5. Speed indicator (table stakes, easy addition)
6. Pause/resume button (differentiator, v1.2)

---

## MVP Recommendation for v1.1

**Prioritize (Table Stakes):**
1. Chunked upload with 5MB chunks (works through Cloudflare 100MB limit)
2. Overall progress bar with smooth updates
3. Automatic retry with exponential backoff (3 attempts)
4. Clear error messages with retry button
5. Cancel button (immediate, no confirmation)
6. Upload speed + time remaining indicator
7. Resume after page refresh (localStorage-based)

**Defer to v1.2:**
- Pause/resume button (user-initiated pause)
- Background upload via Service Worker
- Parallel chunk uploads

**Explicitly Exclude:**
- Per-chunk UI
- Chunk size configuration
- Upload history persistence
- Confirmation dialogs on cancel

---

## Sources

### Primary Sources (HIGH confidence)
- [tus.io - Resumable upload protocol](https://tus.io/protocols/resumable-upload)
- [Uppy Documentation - Progress bar](https://uppy.io/docs/progress-bar/)
- [Uppy Documentation - Dashboard](https://uppy.io/docs/dashboard/)
- [Uploadcare - UX best practices for file uploader](https://uploadcare.com/blog/file-uploader-ux-best-practices/)
- [Uploadcare - How to handle large file uploads](https://uploadcare.com/blog/handling-large-file-uploads/)

### Secondary Sources (MEDIUM confidence)
- [Transloadit - Optimizing file uploads with chunking](https://transloadit.com/devtips/optimizing-online-file-uploads-with-chunking-and-parallel-uploads/)
- [FileStack - Document Upload Apps Best Practices](https://blog.filestack.com/document-upload-apps-key-features-and-best-practices/)
- [FileStack - Complete Guide to Handling Large File Uploads](https://blog.filestack.com/complete-guide-handling-large-file-uploads/)
- [FastPix - Pause and Resume for Large Video Uploads](https://www.fastpix.io/blog/how-to-allow-users-to-upload-large-videos-with-pause-and-resume-features)
- [PatternFly - Multiple file upload design guidelines](https://www.patternfly.org/components/file-upload/multiple-file-upload/design-guidelines/)

### UX Pattern Sources (MEDIUM confidence)
- [NN/g - Confirmation Dialogs](https://www.nngroup.com/articles/confirmation-dialog/)
- [NN/g - Cancel vs Close](https://www.nngroup.com/articles/cancel-vs-close/)
- [LogRocket - How to design nondestructive cancel buttons](https://blog.logrocket.com/ux-design/how-to-design-nondestructive-cancel-buttons/)
- [AWS - Retry with backoff pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html)
- [Google Cloud - Retry strategy](https://cloud.google.com/storage/docs/retry-strategy)

### Community Sources (LOW confidence - used for ecosystem survey only)
- [DEV.to - How to handle large file uploads](https://dev.to/leapcell/how-to-handle-large-file-uploads-without-losing-your-mind-3dck)
- [Medium - Chunked Resumable Uploads for Video](https://aditya007.medium.com/why-chunked-resumable-uploads-are-a-game-changer-for-video-processing-0554f2a36a98)
- [Medium - Large Audio/Video upload system design](https://medium.com/@aditimishra_541/large-audio-video-upload-system-design-807af7f53f01)
