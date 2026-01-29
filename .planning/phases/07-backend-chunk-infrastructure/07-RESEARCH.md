# Phase 7: Backend Chunk Infrastructure - Research

**Researched:** 2026-01-29
**Domain:** TUS protocol server integration with FastAPI for chunked file uploads
**Confidence:** HIGH

## Summary

This phase implements the backend infrastructure for receiving chunked uploads via the TUS (resumable upload) protocol. The decision to use TUS with tuspyserver has been locked from prior v1.1 research. The backend must receive 50MB chunks, store them to disk (not memory), track upload sessions, assemble files when complete, trigger transcription automatically, and clean up stale sessions.

The implementation integrates tuspyserver (v4.2.3) as a FastAPI router. tuspyserver handles all TUS protocol details (session creation, chunk storage, offset tracking, resumability) and provides hooks for post-upload processing. The post-upload hook triggers the existing `process_audio_common` function used by `/speech-to-text`.

**Primary recommendation:** Mount tuspyserver's TUS router at `/uploads/`, configure the `on_upload_complete` hook to trigger transcription, and add APScheduler for session cleanup.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **tuspyserver** | 4.2.3 | TUS protocol server for FastAPI | Native FastAPI integration, dependency injection hooks, automatic chunk handling, active maintenance (Nov 2025 release) |
| **APScheduler** | 3.10.x | Background job scheduling | Already used in Python ecosystem, simple API for periodic cleanup jobs |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **aiofiles** | 23.x | Async file operations | If custom file assembly needed (tuspyserver handles this) |
| **python-magic** | (existing) | MIME type validation | Validate assembled file before transcription |

### Already in Project (Reuse)
| Component | Purpose |
|-----------|---------|
| `streaming-form-data` | Streaming file parsing (existing, different flow) |
| `process_audio_common` | Full transcription pipeline (REUSE for post-upload) |
| `ProgressEmitter` | WebSocket progress updates (REUSE for transcription progress) |
| `validate_magic_bytes` | File content validation (REUSE on assembled file) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tuspyserver | fastapi-tusd | Less maintained (May 2024 last release), tuspyserver is more active |
| tuspyserver | Custom chunking | Reinventing TUS protocol, more code to maintain, proven patterns exist |
| APScheduler | Celery Beat | Overkill for single cleanup job, adds Redis dependency |

**Installation:**
```bash
pip install tuspyserver==4.2.3 apscheduler==3.10.4
```

## Architecture Patterns

### Recommended Project Structure
```
app/
  api/
    tus_upload_api.py       # TUS router mount and hooks
  services/
    upload_session_service.py  # Upload-to-transcription bridge
  infrastructure/
    scheduler/
      __init__.py
      cleanup_scheduler.py  # APScheduler for session cleanup
```

### Pattern 1: TUS Router with Dependency Injection Hook
**What:** Use tuspyserver's `upload_complete_dep` for injecting services into the completion handler
**When to use:** When you need database access, current user, or other FastAPI dependencies in the hook
**Example:**
```python
# Source: https://pypi.org/project/tuspyserver/ (verified)
from fastapi import Depends
from tuspyserver import create_tus_router
from typing import Callable

def create_upload_complete_hook(
    repository: ITaskRepository = Depends(get_task_repository),
    file_service: FileService = Depends(get_file_service),
) -> Callable[[str, dict], None]:
    """Factory that returns upload completion handler with injected deps."""
    async def handler(file_path: str, metadata: dict):
        filename = metadata.get("filename", "unknown")
        # Validate assembled file
        is_valid, msg, detected = validate_magic_bytes(Path(file_path), Path(filename).suffix)
        if not is_valid:
            raise ValidationError(f"Invalid file: {msg}")

        # Trigger transcription (reuse existing pipeline)
        await trigger_transcription(file_path, metadata, repository)

    return handler

tus_router = create_tus_router(
    files_dir="./uploads/tus",
    max_size=5 * 1024 * 1024 * 1024,  # 5GB max total file
    days_to_keep=1,  # 1 day retention (cleanup also handled by scheduler)
    upload_complete_dep=create_upload_complete_hook,
)
```

### Pattern 2: Simple Callback (No DI)
**What:** Use `on_upload_complete` for simpler cases without dependency injection
**When to use:** When you don't need FastAPI dependencies in the handler
**Example:**
```python
# Source: https://github.com/edihasaj/tuspyserver
def on_upload_complete(file_path: str, metadata: dict):
    """Simple completion handler without DI."""
    print(f"Upload complete: {file_path}")
    print(f"Metadata: {metadata}")

tus_router = create_tus_router(
    files_dir="./uploads/tus",
    on_upload_complete=on_upload_complete,
)
```

### Pattern 3: Transcription Trigger Service
**What:** Separate service that bridges TUS completion to existing transcription pipeline
**When to use:** To maintain SRP and allow testing
**Example:**
```python
# app/services/upload_session_service.py
from app.audio import get_audio_duration, process_audio_file
from app.services import process_audio_common
from app.schemas import SpeechToTextProcessingParams

class UploadSessionService:
    """Bridges TUS uploads to transcription pipeline."""

    def __init__(self, repository: ITaskRepository):
        self.repository = repository

    async def start_transcription(
        self,
        file_path: Path,
        metadata: dict,
        background_tasks: BackgroundTasks,
    ) -> str:
        """Trigger transcription for completed TUS upload."""
        # Load audio (same as audio_api.py)
        audio = process_audio_file(str(file_path))
        audio_duration = get_audio_duration(audio)

        # Create task entity
        task = DomainTask(
            uuid=str(uuid4()),
            status=TaskStatus.processing,
            file_name=metadata.get("filename", file_path.name),
            audio_duration=audio_duration,
            language=metadata.get("language", "en"),
            task_type=TaskType.full_process,
            # ... other fields from metadata
        )

        identifier = self.repository.add(task)

        # Build params and schedule background task
        audio_params = SpeechToTextProcessingParams(...)
        background_tasks.add_task(process_audio_common, audio_params)

        return identifier
```

### Pattern 4: CORS Configuration for TUS
**What:** Expose TUS-specific headers through CORS middleware
**When to use:** Always required when frontend is on different origin
**Example:**
```python
# Source: https://github.com/edihasaj/tuspyserver (verified)
from fastapi.middleware.cors import CORSMiddleware

# CRITICAL: These headers MUST be exposed for TUS to work
TUS_HEADERS = [
    "Location",
    "Upload-Offset",
    "Upload-Length",
    "Tus-Resumable",
    "Tus-Version",
    "Tus-Extension",
    "Tus-Max-Size",
    "Upload-Expires",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=TUS_HEADERS,  # REQUIRED
)
```

### Anti-Patterns to Avoid
- **Loading chunks into memory:** tuspyserver streams to disk. Don't override this behavior.
- **Custom session tracking:** tuspyserver tracks offsets internally. Don't duplicate.
- **Synchronous file validation in hook:** Use async or schedule as background task.
- **Blocking in upload_complete hook:** Long processing blocks response. Schedule background work.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chunk offset tracking | Manual byte counting | tuspyserver's `Upload-Offset` | Protocol-compliant, handles resume |
| Upload session creation | Custom UUID + storage | tuspyserver's POST /files | Returns Location header per TUS spec |
| Resumability | Custom HEAD endpoint | tuspyserver's HEAD handler | Returns correct offset for client resume |
| Chunk file naming | Manual temp file management | tuspyserver's files_dir | Automatic naming, cleanup integration |
| Expiration tracking | Database timestamp checks | tuspyserver's `days_to_keep` + `remove_expired_files()` | Built-in, just schedule it |

**Key insight:** The TUS protocol has many edge cases (partial chunks, duplicate uploads, client disconnects, resume after server restart). tuspyserver handles all of these. Custom implementations inevitably miss cases.

## Common Pitfalls

### Pitfall 1: Missing CORS expose_headers
**What goes wrong:** Frontend cannot read `Location` header after upload creation, breaking the flow.
**Why it happens:** CORS blocks access to non-standard headers by default. TUS requires custom headers.
**How to avoid:** Always include `expose_headers` with all TUS headers in CORS middleware.
**Warning signs:** Browser console shows "refused to get unsafe header 'Location'" error.

### Pitfall 2: Upload-Complete Hook Blocks Response
**What goes wrong:** Transcription starts synchronously in hook, causing 30+ second response time, Cloudflare timeout.
**Why it happens:** Hook runs before response is sent. Long processing blocks everything.
**How to avoid:** Use `BackgroundTasks` or schedule work asynchronously. Return 202 immediately.
**Warning signs:** Upload appears to hang at 100%, then times out.

### Pitfall 3: Memory Exhaustion During Large File Assembly
**What goes wrong:** Server OOM when assembling 500MB file.
**Why it happens:** Some code loads entire file into memory for validation.
**How to avoid:** tuspyserver handles assembly. For validation, use streaming/seeking.
**Warning signs:** Works with 50MB files, crashes with 200MB files.

### Pitfall 4: Orphaned Upload Sessions
**What goes wrong:** Disk fills up with incomplete uploads.
**Why it happens:** User closes browser mid-upload, no cleanup runs.
**How to avoid:**
1. Set `days_to_keep=1` in tuspyserver config
2. Schedule `remove_expired_files()` via APScheduler every hour
3. Also check/clean on startup
**Warning signs:** Upload directory size grows continuously.

### Pitfall 5: Cloudflare Rate Limiting
**What goes wrong:** Uploads fail with 429 after ~10-20 chunks.
**Why it happens:** Rapid PATCH requests from same IP trigger rate limiting.
**How to avoid:** Configure Cloudflare WAF rule to bypass rate limiting for `/uploads/` path. (Phase 10 concern, document here)
**Warning signs:** Works locally, fails through Cloudflare.

### Pitfall 6: Missing Metadata in Post-Upload Hook
**What goes wrong:** Cannot determine original filename or language for transcription.
**Why it happens:** Frontend didn't send metadata, or metadata key names mismatch.
**How to avoid:**
1. Define metadata schema: `filename`, `filetype`, `language`, `model`
2. Frontend sends via `metadata` option in tus-js-client
3. Hook receives in `metadata` dict parameter
**Warning signs:** All uploaded files named with UUID only, wrong language used.

## Code Examples

Verified patterns from official sources:

### TUS Router Setup
```python
# Source: https://pypi.org/project/tuspyserver/ (verified)
# app/api/tus_upload_api.py

from fastapi import APIRouter, BackgroundTasks, Depends
from tuspyserver import create_tus_router

from app.core.upload_config import UPLOAD_DIR
from app.api.dependencies import get_task_repository
from app.services.upload_session_service import UploadSessionService

# Storage for TUS uploads (separate from streaming uploads)
TUS_UPLOAD_DIR = UPLOAD_DIR / "tus"

def create_upload_complete_hook(
    background_tasks: BackgroundTasks,
    repository=Depends(get_task_repository),
):
    """DI factory for upload completion handler."""
    service = UploadSessionService(repository)

    async def handler(file_path: str, metadata: dict):
        # Trigger transcription in background
        await service.start_transcription(
            file_path=Path(file_path),
            metadata=metadata,
            background_tasks=background_tasks,
        )

    return handler

# Create TUS router
tus_router = create_tus_router(
    prefix="files",
    files_dir=str(TUS_UPLOAD_DIR),
    max_size=5 * 1024 * 1024 * 1024,  # 5GB per CONTEXT.md
    days_to_keep=1,
    upload_complete_dep=create_upload_complete_hook,
)

# Export for main.py
tus_upload_router = APIRouter(prefix="/uploads", tags=["TUS Upload"])
tus_upload_router.include_router(tus_router)
```

### Session Cleanup Scheduler
```python
# Source: APScheduler documentation + tuspyserver
# app/infrastructure/scheduler/cleanup_scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tuspyserver import remove_expired_files

from app.core.logging import logger
from app.core.upload_config import UPLOAD_DIR

TUS_UPLOAD_DIR = UPLOAD_DIR / "tus"
CLEANUP_INTERVAL_MINUTES = 10  # Per requirements: 10 min expiry

scheduler = AsyncIOScheduler()

def cleanup_expired_uploads():
    """Remove expired TUS upload sessions."""
    try:
        removed = remove_expired_files(str(TUS_UPLOAD_DIR))
        if removed:
            logger.info("Cleaned up %d expired upload sessions", len(removed))
    except Exception as e:
        logger.error("Failed to cleanup expired uploads: %s", e)

def start_cleanup_scheduler():
    """Start the background scheduler for cleanup jobs."""
    scheduler.add_job(
        cleanup_expired_uploads,
        "interval",
        minutes=CLEANUP_INTERVAL_MINUTES,
        id="cleanup_expired_uploads",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Started upload cleanup scheduler (interval: %d min)", CLEANUP_INTERVAL_MINUTES)

def stop_cleanup_scheduler():
    """Stop the scheduler gracefully."""
    scheduler.shutdown(wait=False)
```

### Integration in main.py
```python
# app/main.py (additions)
from app.api.tus_upload_api import tus_upload_router
from app.infrastructure.scheduler.cleanup_scheduler import (
    start_cleanup_scheduler,
    stop_cleanup_scheduler,
)

# In lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup ...
    start_cleanup_scheduler()
    yield
    stop_cleanup_scheduler()
    # ... existing shutdown ...

# Include TUS router
app.include_router(tus_upload_router)  # Mounts at /uploads/files
```

### CORS Update for TUS Headers
```python
# app/main.py (update existing CORS or add new)
from fastapi.middleware.cors import CORSMiddleware

TUS_HEADERS = [
    "Location",
    "Upload-Offset",
    "Upload-Length",
    "Tus-Resumable",
    "Tus-Version",
    "Tus-Extension",
    "Tus-Max-Size",
    "Upload-Expires",
]

# Must be added BEFORE routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=TUS_HEADERS,
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom chunk endpoints | TUS protocol libraries | 2020+ | Standardized resumability, client ecosystem |
| In-memory chunk assembly | Streaming to disk | Always best practice | Handles large files without OOM |
| Manual cleanup cron | APScheduler in-process | FastAPI pattern | No external scheduler dependency |

**Deprecated/outdated:**
- `fastapi-tusd`: Less maintained than tuspyserver, use tuspyserver instead
- Manual `Content-Range` parsing: TUS protocol handles this, don't reinvent

## Open Questions

Things that couldn't be fully resolved:

1. **Metadata key naming convention**
   - What we know: tus-js-client sends metadata, tuspyserver receives it
   - What's unclear: Exact key names need agreement with frontend (Phase 8)
   - Recommendation: Define interface: `{filename, filetype, language, model}`. Document in Phase 7, implement matching in Phase 8.

2. **Error propagation from upload_complete hook**
   - What we know: Hook runs after upload, before response
   - What's unclear: How errors in hook affect client response
   - Recommendation: Wrap hook in try/catch, log errors, return success anyway (file is uploaded). Transcription errors handled via WebSocket.

3. **tuspyserver file naming scheme**
   - What we know: tuspyserver manages files in `files_dir`
   - What's unclear: Exact filename pattern, whether UUID or other
   - Recommendation: Accept whatever tuspyserver provides in `file_path` param, use metadata for original filename.

## Sources

### Primary (HIGH confidence)
- [tuspyserver PyPI](https://pypi.org/project/tuspyserver/) - Version 4.2.3, Nov 2025, verified API
- [tuspyserver GitHub](https://github.com/edihasaj/tuspyserver) - Integration patterns, hook examples
- [TUS Protocol Specification](https://tus.io/protocols/resumable-upload) - Authoritative protocol reference

### Secondary (MEDIUM confidence)
- [tus-js-client API](https://github.com/tus/tus-js-client/blob/main/docs/api.md) - Frontend counterpart (Phase 8)
- [APScheduler Documentation](https://apscheduler.readthedocs.io/) - Scheduler patterns
- [FastAPI CORS Middleware](https://fastapi.tiangolo.com/tutorial/cors/) - CORS configuration

### Tertiary (LOW confidence)
- Community discussions on chunked uploads - General patterns, not tuspyserver-specific

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - tuspyserver verified on PyPI, active maintenance confirmed
- Architecture: HIGH - Patterns from official docs, existing codebase integration points identified
- Pitfalls: HIGH - Documented from prior research (PITFALLS.md) and official TUS protocol resources

**Research date:** 2026-01-29
**Valid until:** 2026-02-28 (30 days - stable library, protocol-based)
