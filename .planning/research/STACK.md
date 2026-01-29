# Stack Research: Chunked Uploads

**Project:** WhisperX Transcription App
**Researched:** 2026-01-29
**Focus:** Bypassing Cloudflare 100MB limit with chunked uploads
**Overall Confidence:** HIGH

## Executive Summary

To bypass Cloudflare's 100MB per-request limit for files up to 500MB+, the recommended approach is implementing the **TUS resumable upload protocol** using **tus-js-client** on the frontend and **tuspyserver** on the backend. This provides standardized resumable uploads, automatic retry on failure, and proven Cloudflare compatibility when chunk sizes are kept under 100MB.

---

## Recommended Additions

### Frontend

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **tus-js-client** | ^4.3.1 | TUS protocol client | Industry standard for resumable uploads. Pure JS, works in browsers/Node. Requires Node 18+. Configured chunkSize bypasses Cloudflare limit. |

**Installation:**
```bash
npm install tus-js-client@^4.3.1
```

**Why tus-js-client:**
- **Battle-tested protocol** - Used by Cloudflare, Vimeo, Supabase
- **Automatic resume** - Survives network interruptions without re-uploading
- **Configurable chunks** - Set to 50-90MB to stay under Cloudflare's 100MB limit
- **Progress tracking** - Built-in `onProgress` callback integrates with existing UI
- **Retry logic** - Configurable `retryDelays` for flaky connections (default: `[0, 1000, 3000, 5000]`)
- **Minimal footprint** - No UI dependencies, integrates with existing react-dropzone

### Backend

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **tuspyserver** | ^4.2.3 | TUS protocol server | FastAPI router with dependency injection hooks. Released Nov 2025, actively maintained. Only requires fastapi>=0.110. |

**Installation:**
```bash
pip install tuspyserver==4.2.3
```

**Why tuspyserver:**
- **Native FastAPI integration** - Drops in as a router, uses FastAPI's dependency injection
- **Minimal dependencies** - Only requires `fastapi>=0.110` (already have 0.128.0)
- **Built-in cleanup** - Configurable expiration (default 5 days), `remove_expired_files()` for scheduled cleanup
- **Upload hooks** - Dependency injection for post-upload processing (trigger transcription)
- **Metadata support** - Stores filename/filetype for reconstruction

---

## Integration Points

### Frontend Integration with react-dropzone

react-dropzone handles file selection; tus-js-client handles chunked upload. They compose naturally:

```typescript
// Existing: react-dropzone provides File objects via onDrop
// New: tus-js-client uploads those files in chunks

import { useDropzone } from 'react-dropzone';
import * as tus from 'tus-js-client';

const onDrop = useCallback((acceptedFiles: File[]) => {
  acceptedFiles.forEach((file) => {
    const upload = new tus.Upload(file, {
      endpoint: `${BACKEND_URL}/uploads/`,
      chunkSize: 50 * 1024 * 1024, // 50MB chunks (under Cloudflare 100MB limit)
      retryDelays: [0, 1000, 3000, 5000],
      metadata: {
        filename: file.name,
        filetype: file.type,
      },
      onProgress: (bytesUploaded, bytesTotal) => {
        const percentage = (bytesUploaded / bytesTotal * 100).toFixed(2);
        // Update existing progress UI
      },
      onSuccess: () => {
        // File uploaded - URL available at upload.url
        // Trigger transcription via existing WebSocket flow
      },
      onError: (error) => {
        // Handle error - TUS will auto-retry based on retryDelays
      },
    });
    upload.start();
  });
}, []);

const { getRootProps, getInputProps } = useDropzone({ onDrop });
```

### Backend Integration with FastAPI

tuspyserver provides a router that mounts alongside existing endpoints:

```python
# app/main.py or router file
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tuspyserver import create_tus_router

app = FastAPI()

# CRITICAL: Expose TUS headers through CORS for chunked uploads
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Location",
        "Upload-Offset",
        "Upload-Length",
        "Tus-Resumable",
        "Tus-Version",
        "Tus-Extension",
        "Tus-Max-Size",
    ],
)

# Mount TUS upload router
app.include_router(
    create_tus_router(
        files_dir="./uploads",
        days_to_keep=5,  # Auto-expire incomplete uploads
    ),
    prefix="/uploads",
)
```

### Post-Upload Hook for Transcription

tuspyserver supports dependency injection for post-upload processing:

```python
from tuspyserver import create_tus_router
from fastapi import Depends

async def on_upload_complete(file_path: str, metadata: dict):
    """Trigger transcription after successful upload."""
    # Queue transcription job using existing infrastructure
    # Connect to existing WebSocket progress system
    pass

app.include_router(
    create_tus_router(
        files_dir="./uploads",
        on_upload_complete=on_upload_complete,
    ),
    prefix="/uploads",
)
```

### WebSocket Progress Integration

The existing WebSocket infrastructure remains unchanged. Flow becomes:

1. **Upload phase**: tus-js-client `onProgress` updates UI with upload %
2. **Processing phase**: Existing WebSocket updates UI with transcription progress
3. **Complete**: Existing result delivery mechanism

---

## Cloudflare Compatibility

**Critical constraint:** Cloudflare proxies reject requests >100MB.

**Solution:** Configure `chunkSize` in tus-js-client:

| Chunk Size | Cloudflare Compatible | Performance Notes |
|------------|----------------------|-------------------|
| 50MB | Yes | Safe margin, more requests |
| 90MB | Yes | Fewer requests, closer to limit |
| 100MB | No | Rejected by Cloudflare |
| Infinity (default) | No | Single request fails for large files |

**Recommended:** `chunkSize: 50 * 1024 * 1024` (50MB) for safety margin.

**Total file size limit:** Cloudflare's cache limit is ~512MB for reassembled files. Files >512MB may require Cloudflare bypass (direct to origin) or Cloudflare Stream (separate service).

---

## Session Management / Resume Capability

TUS protocol handles session management automatically:

| Concern | TUS Solution | Notes |
|---------|--------------|-------|
| **Upload ID** | Server-generated URL in `Location` header | Client stores for resume |
| **Progress tracking** | `Upload-Offset` header | Server tracks bytes received |
| **Resume after failure** | Client calls `HEAD` to get offset, resumes from there | Automatic in tus-js-client |
| **Expired uploads** | Server returns 404/410, client starts fresh | tuspyserver: 5-day default |

**Client-side persistence** (optional, for browser refresh survival):

```typescript
const upload = new tus.Upload(file, {
  // Store upload URL in localStorage for resume after page refresh
  storeFingerprintForResuming: true,
  // Custom fingerprint for matching files
  fingerprint: (file) => `${file.name}-${file.size}-${file.lastModified}`,
});
```

---

## Rejected Alternatives

### 1. Uppy (@uppy/core + @uppy/tus)

| Aspect | Assessment |
|--------|------------|
| **What it is** | Full-featured upload UI library with TUS support |
| **Version** | 5.2.2 (Sept 2025 release) |
| **Why rejected** | **Overkill** - Includes Dashboard UI, file preview, cloud providers. You already have react-dropzone UI. Would replace working UI code unnecessarily. |
| **When to use** | Greenfield projects needing complete upload UI |

### 2. @rpldy/chunked-uploady

| Aspect | Assessment |
|--------|------------|
| **What it is** | React-native chunked upload with Content-Range headers |
| **Version** | ~1.13.0 |
| **Why rejected** | **Non-standard protocol** - Uses custom Content-Range chunking, not TUS. Less ecosystem support. Server must implement custom chunk reassembly. No automatic resume on network failure. |
| **When to use** | Simple chunking without resume requirement |

### 3. Custom File.slice() Implementation

| Aspect | Assessment |
|--------|------------|
| **What it is** | Manual chunking with fetch/axios |
| **Why rejected** | **Reinventing the wheel** - Must build: chunk tracking, resume logic, retry logic, progress aggregation, server reassembly. TUS protocol solves all of this. |
| **When to use** | Highly custom requirements not covered by TUS extensions |

### 4. fastapi-tusd

| Aspect | Assessment |
|--------|------------|
| **What it is** | Alternative TUS server for FastAPI |
| **Version** | 0.100.2 (May 2024) |
| **Why rejected** | **Less maintained** - 23 commits total, last release May 2024. tuspyserver is more actively maintained (Nov 2025 release) with better FastAPI integration patterns. |
| **When to use** | If you need S3 storage backend (partial support) |

### 5. S3 Multipart Upload (Direct)

| Aspect | Assessment |
|--------|------------|
| **What it is** | Upload directly to S3 with presigned URLs |
| **Why rejected** | **Different architecture** - Bypasses your FastAPI server entirely. Good for CDN delivery, but you need files on server for WhisperX processing. Would require downloading from S3 before transcription. |
| **When to use** | Large-scale systems with separate processing workers |

---

## Version Compatibility Matrix

| Component | Current Version | Required For Chunked Uploads | Compatible |
|-----------|-----------------|------------------------------|------------|
| React | 19.2.0 | tus-js-client (any React) | Yes |
| Node.js | (build tool) | tus-js-client 4.x requires Node 18+ | Verify |
| FastAPI | 0.128.0 | tuspyserver requires >=0.110 | Yes |
| Python | 3.11 | tuspyserver requires >=3.8 | Yes |
| react-dropzone | 14.3.8 | N/A (composable) | Yes |

---

## Migration Path

### Phase 1: Add Dependencies (Low Risk)
```bash
# Frontend
npm install tus-js-client@^4.3.1

# Backend
pip install tuspyserver==4.2.3
```

### Phase 2: Backend Setup
1. Mount TUS router at `/uploads/`
2. Configure CORS to expose TUS headers
3. Set `files_dir` to upload destination
4. Add post-upload hook for transcription trigger

### Phase 3: Frontend Integration
1. Keep react-dropzone for file selection
2. Replace direct upload with tus-js-client
3. Update progress UI to use TUS `onProgress`
4. Add resume capability (optional)

### Phase 4: Existing Flow Preservation
- Keep WebSocket for transcription progress
- Keep existing result delivery
- Only upload mechanism changes

---

## Sources

### Primary (HIGH Confidence)
- [tus-js-client GitHub Releases](https://github.com/tus/tus-js-client/releases) - v4.3.1 confirmed Jan 2025
- [tus-js-client API Documentation](https://github.com/tus/tus-js-client/blob/main/docs/api.md) - chunkSize, retryDelays, onProgress
- [tuspyserver PyPI](https://pypi.org/project/tuspyserver/) - v4.2.3, Nov 2025
- [tuspyserver GitHub](https://github.com/edihasaj/tuspy-fast-api) - FastAPI integration patterns
- [TUS Protocol Specification](https://tus.io/protocols/resumable-upload) - Expiration, resume behavior

### Secondary (MEDIUM Confidence)
- [Cloudflare Stream TUS Docs](https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/) - Chunk size requirements
- [Cloudflare Community: TUS behind proxy](https://community.cloudflare.com/t/upload-with-tus-protocol-returns-413-for-large-videos-623-mb/603198) - 100MB limit confirmation
- [Uppy React Docs](https://uppy.io/docs/react/) - v5.x release info

### Tertiary (LOW Confidence - Community Sources)
- [FastAPI Discussion: Big File Uploads](https://github.com/fastapi/fastapi/discussions/9828) - Chunking patterns
- [Transloadit Blog: Drag and Drop React](https://transloadit.com/devtips/implementing-drag-and-drop-file-upload-in-react/) - TUS integration patterns
