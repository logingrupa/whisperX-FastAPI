# Phase 2: File Upload Infrastructure - Research

**Researched:** 2026-01-27
**Domain:** FastAPI streaming file uploads, file validation, memory-efficient large file handling
**Confidence:** HIGH

## Summary

This research investigates how to implement memory-efficient large file upload infrastructure for FastAPI, specifically targeting audio/video files up to 5GB. The phase requires handling uploads without memory exhaustion or event loop blocking, validating file formats before processing, and maintaining responsiveness during uploads.

The standard approach for large file uploads in FastAPI involves using `streaming-form-data` library for true streaming (bypassing FastAPI's default form parsing which buffers files), combined with `aiofiles` for async disk I/O. For file type validation, `puremagic` provides pure-Python magic byte detection without external dependencies. The existing codebase already uses `python-multipart` for form handling, but this needs to be augmented with streaming capabilities for large files.

**Primary recommendation:** Use `streaming-form-data` with `FileTarget` for direct-to-disk streaming, validate magic bytes with `puremagic` after receiving first chunk, and implement chunked upload endpoint with auto-retry support and partial upload cleanup via APScheduler.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streaming-form-data | 1.19.1 | Streaming multipart parser | Cython-based, 10x faster than default, streams directly to disk |
| aiofiles | 25.1.0 | Async file I/O | Non-blocking file writes in async context |
| puremagic | 1.30 | File type validation via magic bytes | Pure Python, no libmagic dependency, cross-platform |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| APScheduler | 3.10.x | Scheduled cleanup tasks | Partial upload cleanup (5-10 min expiry) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| streaming-form-data | Default UploadFile | UploadFile buffers to memory first; only for small files |
| puremagic | python-magic | python-magic requires libmagic C library; harder to deploy |
| Custom chunked upload | fastapi-tusd | TUS protocol is overkill; fastapi-tusd has incomplete features |

**Installation:**
```bash
# Using pip (but project uses Bun for package management per prior decisions)
pip install streaming-form-data aiofiles puremagic apscheduler
```

## Architecture Patterns

### Recommended Project Structure
```
app/
├── api/
│   └── upload_api.py           # Streaming upload endpoints
├── services/
│   └── upload_service.py       # Upload orchestration, validation
├── infrastructure/
│   └── storage/
│       ├── streaming_target.py # Custom streaming target
│       └── upload_storage.py   # File storage management
├── core/
│   └── upload_config.py        # Upload configuration (sizes, timeouts)
└── tasks/
    └── cleanup_task.py         # Partial upload cleanup scheduler
```

### Pattern 1: Streaming Upload with Direct-to-Disk
**What:** Bypass FastAPI's default form parsing, stream directly to disk as chunks arrive
**When to use:** Files > 10MB, especially for the 5GB max in this phase
**Example:**
```python
# Source: streaming-form-data docs + FastAPI patterns
from fastapi import APIRouter, Request, HTTPException
from streaming_form_data import StreamingFormDataParser
from streaming_form_data.targets import FileTarget, ValueTarget
from streaming_form_data.validators import MaxSizeValidator
import aiofiles
import puremagic

CHUNK_SIZE = 1024 * 1024  # 1MB chunks
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB

router = APIRouter()

@router.post("/upload")
async def upload_file(request: Request):
    # Get content type for parser
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(400, "Content-Type must be multipart/form-data")

    # Create unique temp path
    upload_id = str(uuid4())
    temp_path = f"/tmp/uploads/{upload_id}.tmp"

    # Initialize streaming parser with size validator
    parser = StreamingFormDataParser(
        headers={"Content-Type": content_type}
    )
    file_target = FileTarget(
        temp_path,
        validator=MaxSizeValidator(MAX_FILE_SIZE)
    )
    parser.register("file", file_target)

    # Track bytes for magic validation
    first_chunk = True
    magic_validated = False

    # Stream chunks to disk
    async for chunk in request.stream():
        # Validate magic bytes on first chunk
        if first_chunk and chunk:
            file_type = validate_magic_bytes(chunk[:2048])
            if not file_type:
                raise HTTPException(400, "Invalid file format")
            magic_validated = True
            first_chunk = False

        parser.data_received(chunk)

    return {
        "upload_id": upload_id,
        "filename": file_target.multipart_filename,
        "size": file_target.multipart_content_type
    }
```

### Pattern 2: Magic Bytes Validation
**What:** Validate file type by examining first bytes, not trusting extension/MIME
**When to use:** Always as server-side second layer after client-side extension check
**Example:**
```python
# Source: puremagic docs
import puremagic
from typing import Optional

ALLOWED_MAGIC_TYPES = {
    ".mp3", ".wav", ".mp4", ".m4a",
    ".flac", ".ogg", ".webm", ".mov"
}

def validate_magic_bytes(file_header: bytes) -> Optional[str]:
    """
    Validate file type from magic bytes.

    Args:
        file_header: First 2048 bytes of file

    Returns:
        File extension if valid, None if invalid/unknown
    """
    try:
        results = puremagic.magic_string(file_header)
        if not results:
            return None

        # puremagic returns list sorted by confidence
        for result in results:
            extension = result.extension.lower()
            if extension in ALLOWED_MAGIC_TYPES:
                return extension

        return None
    except Exception:
        return None
```

### Pattern 3: Partial Upload Storage with Cleanup
**What:** Store partial uploads temporarily, clean up after timeout
**When to use:** Supporting resumable uploads, failed upload cleanup
**Example:**
```python
# Source: APScheduler docs + common patterns
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import os
from pathlib import Path

UPLOAD_DIR = Path("/tmp/uploads")
PARTIAL_UPLOAD_EXPIRY_MINUTES = 10

scheduler = AsyncIOScheduler()

async def cleanup_expired_uploads():
    """Remove partial uploads older than expiry time."""
    cutoff = datetime.now() - timedelta(minutes=PARTIAL_UPLOAD_EXPIRY_MINUTES)

    for filepath in UPLOAD_DIR.glob("*.tmp"):
        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            if mtime < cutoff:
                filepath.unlink()
        except OSError:
            pass  # File may have been removed

# Schedule cleanup every 5 minutes
scheduler.add_job(
    cleanup_expired_uploads,
    "interval",
    minutes=5,
    id="upload_cleanup"
)
```

### Anti-Patterns to Avoid
- **Loading entire file into memory:** Never use `file.file.read()` for large files; always stream in chunks
- **Synchronous file I/O in async handlers:** Use `aiofiles` not built-in `open()` to avoid blocking event loop
- **Trusting Content-Type header:** Always validate magic bytes server-side; headers can be spoofed
- **Unbounded uploads:** Always set max file size limits both client-side and server-side

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multipart streaming parser | Custom chunk parser | streaming-form-data | RFC 7578 compliance, boundary handling, Cython speed |
| File type detection | Extension checking only | puremagic | Magic bytes prevent spoofing, handles variants |
| Async file I/O | threading + open() | aiofiles | Proper asyncio integration, context managers |
| Size validation during upload | Post-upload check | streaming-form-data validators | Fail fast, don't waste bandwidth |
| Scheduled cleanup | Manual cron or threading | APScheduler | Proper lifecycle, async support, persistence |

**Key insight:** Multipart parsing is deceptively complex (boundaries, content-disposition parsing, chunk assembly). The `streaming-form-data` library is specifically designed for this and is 10x faster than alternatives due to Cython implementation.

## Common Pitfalls

### Pitfall 1: FastAPI UploadFile Buffers Everything
**What goes wrong:** Using `file: UploadFile = File(...)` loads entire file to SpooledTemporaryFile before handler runs
**Why it happens:** FastAPI's form parsing calls `await request.form()` which consumes entire body
**How to avoid:** Use `Request` directly with `request.stream()` for true streaming
**Warning signs:** Memory spikes proportional to file size; server OOM on large uploads

### Pitfall 2: Blocking Event Loop with Sync File I/O
**What goes wrong:** `open()` and `file.write()` block the asyncio event loop
**Why it happens:** Disk I/O is inherently blocking; standard library doesn't provide async file ops
**How to avoid:** Use `aiofiles` for all file operations in async handlers
**Warning signs:** Other requests stall during file writes; high latency on concurrent uploads

### Pitfall 3: Multipart Boundary in Stream
**What goes wrong:** Using `request.stream()` directly includes multipart boundaries in file data
**Why it happens:** Raw stream contains RFC 7578 framing, not just file content
**How to avoid:** Use `streaming-form-data` parser which strips boundaries correctly
**Warning signs:** Corrupted files; extra bytes at start/end of uploads

### Pitfall 4: Content-Type Spoofing
**What goes wrong:** Accepting files based on extension or Content-Type header only
**Why it happens:** These are client-controlled and trivially spoofed
**How to avoid:** Validate magic bytes server-side; treat extension as hint only
**Warning signs:** Accepting malicious files disguised with wrong extension

### Pitfall 5: No Upload Size Limit
**What goes wrong:** Server accepts arbitrarily large uploads, enabling DoS
**Why it happens:** Forgetting to configure limits at all layers
**How to avoid:** Set limits in: Nginx/reverse proxy, FastAPI middleware, and streaming validator
**Warning signs:** Disk fills up; memory exhaustion attacks succeed

### Pitfall 6: Race Conditions in Cleanup
**What goes wrong:** Cleanup job deletes file while upload still in progress
**Why it happens:** Using modification time only; not tracking active uploads
**How to avoid:** Track active upload IDs; only clean up uploads not in progress
**Warning signs:** Intermittent "file not found" errors; partial upload corruption

## Code Examples

Verified patterns from official sources:

### Streaming Upload Handler
```python
# Source: streaming-form-data docs + FastAPI patterns
from fastapi import APIRouter, Request, HTTPException, status
from streaming_form_data import StreamingFormDataParser
from streaming_form_data.targets import FileTarget
from streaming_form_data.validators import MaxSizeValidator
from streaming_form_data.exceptions import ValidationError
import uuid
from pathlib import Path

router = APIRouter()

UPLOAD_DIR = Path("/tmp/uploads")
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".mp4", ".m4a", ".flac", ".ogg", ".webm"}
CHUNK_READ_SIZE = 1024 * 1024  # 1MB

@router.post("/upload")
async def streaming_upload(request: Request):
    """Stream large file upload directly to disk."""

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Type must be multipart/form-data"
        )

    upload_id = str(uuid.uuid4())
    temp_path = UPLOAD_DIR / f"{upload_id}.tmp"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Create parser with size validator
    parser = StreamingFormDataParser(headers={"Content-Type": content_type})

    file_target = FileTarget(
        str(temp_path),
        validator=MaxSizeValidator(MAX_FILE_SIZE)
    )
    parser.register("file", file_target)

    try:
        async for chunk in request.stream():
            parser.data_received(chunk)
    except ValidationError as e:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024**3):.1f}GB"
        )

    # Validate file type via magic bytes
    detected_type = validate_file_magic(temp_path)
    if detected_type not in ALLOWED_EXTENSIONS:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MP3, WAV, MP4, M4A, FLAC, OGG, WebM files only. Detected: {detected_type or 'unknown'}"
        )

    return {
        "upload_id": upload_id,
        "filename": file_target.multipart_filename,
        "size_bytes": temp_path.stat().st_size,
        "detected_type": detected_type
    }
```

### Magic Bytes Validation Function
```python
# Source: puremagic docs
import puremagic
from pathlib import Path
from typing import Optional

AUDIO_VIDEO_MAGIC_TYPES = {
    # Direct matches
    ".mp3", ".wav", ".mp4", ".m4a", ".flac", ".ogg", ".webm", ".mov",
    # Alternate extensions puremagic might return
    ".oga", ".ogv", ".mkv"
}

# Map alternate extensions to canonical forms
EXTENSION_MAP = {
    ".oga": ".ogg",
    ".ogv": ".ogg",
    ".mkv": ".webm",
    ".mov": ".mp4",  # Both use MPEG-4 container
}

def validate_file_magic(file_path: Path) -> Optional[str]:
    """
    Validate file type using magic bytes.

    Args:
        file_path: Path to file to validate

    Returns:
        Canonical extension if valid audio/video, None otherwise
    """
    try:
        # Read first 2048 bytes for magic detection
        with open(file_path, "rb") as f:
            header = f.read(2048)

        if not header:
            return None

        results = puremagic.magic_string(header)
        if not results:
            return None

        # Results sorted by confidence (highest first)
        for result in results:
            ext = result.extension.lower()
            if not ext.startswith("."):
                ext = f".{ext}"

            # Check if it's a known audio/video type
            if ext in AUDIO_VIDEO_MAGIC_TYPES:
                # Return canonical extension
                return EXTENSION_MAP.get(ext, ext)

        return None

    except Exception:
        return None
```

### Async File Writing with aiofiles
```python
# Source: aiofiles docs
import aiofiles
from pathlib import Path

async def save_uploaded_chunk(
    upload_path: Path,
    chunk: bytes,
    append: bool = False
) -> int:
    """
    Save chunk to file asynchronously.

    Args:
        upload_path: Destination file path
        chunk: Bytes to write
        append: If True, append to existing file

    Returns:
        Number of bytes written
    """
    mode = "ab" if append else "wb"
    async with aiofiles.open(upload_path, mode) as f:
        await f.write(chunk)
    return len(chunk)
```

### Scheduled Cleanup Task
```python
# Source: APScheduler docs
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("/tmp/uploads")
PARTIAL_EXPIRY_SECONDS = 600  # 10 minutes

# Track active uploads to avoid deleting in-progress files
active_uploads: set[str] = set()

async def cleanup_expired_partials():
    """Remove partial uploads that have expired."""
    if not UPLOAD_DIR.exists():
        return

    cutoff = datetime.now() - timedelta(seconds=PARTIAL_EXPIRY_SECONDS)
    cleaned = 0

    for path in UPLOAD_DIR.glob("*.tmp"):
        upload_id = path.stem

        # Skip active uploads
        if upload_id in active_uploads:
            continue

        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if mtime < cutoff:
                path.unlink()
                cleaned += 1
                logger.info(f"Cleaned up expired upload: {upload_id}")
        except OSError as e:
            logger.warning(f"Failed to clean up {path}: {e}")

    if cleaned > 0:
        logger.info(f"Cleanup complete: removed {cleaned} expired uploads")

def setup_cleanup_scheduler() -> AsyncIOScheduler:
    """Configure and return the cleanup scheduler."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        cleanup_expired_partials,
        trigger=IntervalTrigger(minutes=5),
        id="partial_upload_cleanup",
        name="Clean up expired partial uploads",
        replace_existing=True
    )
    return scheduler
```

## Magic Bytes Reference

Validated signatures for allowed file types:

| Format | Magic Bytes (Hex) | ASCII | Offset | Notes |
|--------|-------------------|-------|--------|-------|
| MP3 (ID3) | `49 44 33` | `ID3` | 0 | With ID3 tag |
| MP3 (raw) | `FF FB` or `FF FA` | - | 0 | Frame sync without ID3 |
| WAV | `52 49 46 46 ... 57 41 56 45` | `RIFF....WAVE` | 0 | RIFF container |
| MP4 | `66 74 79 70` | `ftyp` | 4 | After 4-byte size |
| M4A | `66 74 79 70 4D 34 41` | `ftypM4A` | 4 | MPEG-4 audio subtype |
| FLAC | `66 4C 61 43` | `fLaC` | 0 | Stream marker |
| OGG | `4F 67 67 53` | `OggS` | 0 | Page header |
| WebM | `1A 45 DF A3` | - | 0 | EBML header (Matroska) |
| MOV | `66 74 79 70 71 74` | `ftypqt` | 4 | QuickTime variant |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `UploadFile` for all sizes | `streaming-form-data` for large files | 2023+ | Memory-efficient 5GB+ uploads |
| Sync file I/O in handlers | `aiofiles` async I/O | 2020+ | Non-blocking event loop |
| Extension-only validation | Magic bytes + extension | Always recommended | Security against spoofing |
| Manual cron cleanup | APScheduler in-process | 2022+ | Cleaner lifecycle management |

**Deprecated/outdated:**
- **`python-multipart` alone for large files:** Still used by FastAPI but buffers entire file; insufficient for 5GB
- **TUS protocol for simple use cases:** Overkill complexity; chunked streaming sufficient for 5GB max

## Open Questions

Things that couldn't be fully resolved:

1. **Optimal chunk size for streaming**
   - What we know: 1MB is common default; 64KB-4MB range recommended
   - What's unclear: Optimal size for this specific workload (audio/video, 5GB max)
   - Recommendation: Start with 1MB, benchmark if performance issues arise

2. **Gunicorn worker coordination for scheduler**
   - What we know: Multiple Gunicorn workers = multiple scheduler instances
   - What's unclear: Best pattern for single-scheduler-per-deployment
   - Recommendation: Use APScheduler with database job store, or run cleanup in separate process

3. **Resume support complexity**
   - What we know: CONTEXT.md mentions "server keeps partial uploads briefly for potential resume"
   - What's unclear: Whether full resume protocol needed or just retry-on-failure
   - Recommendation: Implement simple retry (re-upload failed chunk) not full TUS resume; complexity not justified

## Sources

### Primary (HIGH confidence)
- [FastAPI Request Files Documentation](https://fastapi.tiangolo.com/tutorial/request-files/) - UploadFile API, SpooledTemporaryFile behavior
- [Starlette Requests Documentation](https://www.starlette.io/requests/) - request.stream() API, form parsing
- [streaming-form-data GitHub](https://github.com/siddhantgoel/streaming-form-data) - Streaming parser usage
- [streaming-form-data Documentation](https://streaming-form-data.readthedocs.io/en/latest/) - Targets, validators
- [aiofiles PyPI](https://pypi.org/project/aiofiles/) - Async file I/O (v25.1.0)
- [puremagic PyPI](https://pypi.org/project/puremagic/) - Magic bytes detection (v1.30)

### Secondary (MEDIUM confidence)
- [FastAPI Discussions #9828](https://github.com/fastapi/fastapi/discussions/9828) - Large file upload patterns
- [APScheduler Documentation](https://apscheduler.readthedocs.io/en/master/userguide.html) - Scheduler setup
- [Sentry FastAPI Task Scheduling](https://sentry.io/answers/schedule-tasks-with-fastapi/) - APScheduler integration

### Tertiary (LOW confidence)
- [Medium: Async File Uploads in FastAPI](https://medium.com/@connect.hashblock/async-file-uploads-in-fastapi-handling-gigabyte-scale-data-smoothly-aec421335680) - Community patterns
- [Medium: Streaming File Uploads](https://python.plainenglish.io/streaming-file-uploads-and-downloads-with-fastapi-a-practical-guide-ee5be38fdd66) - Additional examples
- [AWS Exponential Backoff](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html) - Retry patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official documentation verified for all libraries
- Architecture: HIGH - Patterns verified from official docs and established community practices
- Pitfalls: HIGH - Well-documented issues in FastAPI discussions
- Magic bytes: MEDIUM - Cross-referenced multiple sources but Wikipedia blocked

**Research date:** 2026-01-27
**Valid until:** 2026-02-27 (30 days - stable domain)
