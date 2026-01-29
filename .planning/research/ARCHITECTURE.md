# Architecture Research: Chunked Uploads Integration

**Domain:** Chunked file uploads for WhisperX transcription app
**Researched:** 2026-01-29
**Confidence:** HIGH
**Constraint:** Cloudflare 100MB limit requires chunking for files > 100MB

## Executive Summary

This research documents how chunked uploads integrate with the existing WhisperX FastAPI + React architecture. The system already has streaming uploads (POST /upload/stream), WebSocket progress tracking, and a transcription pipeline. Chunked uploads add a new flow for large files that bypasses proxy limits while reusing existing infrastructure.

**Key integration points:**
- New chunked upload API endpoints (session create, chunk upload, finalize)
- Reuse existing WebSocket progress infrastructure for upload progress
- Finalize endpoint triggers existing /speech-to-text transcription flow
- Frontend decision layer: small files use existing flow, large files use chunked flow

## Existing Architecture (Reference)

```
Current Flow (files < 100MB):

[React Upload]
     |
     | POST /speech-to-text (multipart)
     v
[FastAPI audio_api.py]
     |
     | Save to temp, create task
     v
[Background Task] -----> [WebSocket /ws/tasks/{id}]
     |                         |
     | Process audio           | Progress updates
     v                         v
[Transcription Pipeline]  [React Progress UI]
```

## New Components

### 1. Upload Session Model (Database)

New table to track chunked upload sessions:

```python
# app/infrastructure/database/models.py (addition)
class UploadSession(Base):
    """Track chunked upload sessions."""
    __tablename__ = "upload_sessions"

    id = Column(String, primary_key=True)  # UUID
    filename = Column(String, nullable=False)
    total_size = Column(BigInteger, nullable=False)
    total_chunks = Column(Integer, nullable=False)
    received_chunks = Column(Integer, default=0)
    status = Column(String, default="uploading")  # uploading, complete, expired, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    # Transcription parameters (stored at session create)
    language = Column(String, nullable=True)
    model = Column(String, nullable=True)
    task_params = Column(JSON, nullable=True)
```

### 2. Chunked Upload API Router

New endpoints for chunked upload flow:

```python
# app/api/chunked_upload_api.py (new file)
chunked_upload_router = APIRouter(prefix="/upload/chunked", tags=["Chunked Upload"])
```

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload/chunked/session` | POST | Create upload session, return session_id |
| `/upload/chunked/{session_id}/chunk` | POST | Upload single chunk (with index) |
| `/upload/chunked/{session_id}/finalize` | POST | Assemble chunks, trigger transcription |
| `/upload/chunked/{session_id}/status` | GET | Check session status (for resume) |
| `/upload/chunked/{session_id}/abort` | DELETE | Cancel upload, cleanup chunks |

### 3. Chunk Storage Directory Structure

```
{UPLOAD_DIR}/
  chunked/
    {session_id}/
      chunk_0000
      chunk_0001
      chunk_0002
      ...
      metadata.json  # Total chunks, filename, etc.
```

### 4. Frontend Chunked Upload Service

```typescript
// frontend/src/lib/api/chunkedUploadApi.ts (new file)
export interface ChunkedUploadOptions {
  file: File;
  chunkSize?: number;  // Default 50MB (under Cloudflare 100MB limit)
  onProgress?: (progress: ChunkProgress) => void;
  language: LanguageCode;
  model: WhisperModel;
}

export interface ChunkProgress {
  uploadedChunks: number;
  totalChunks: number;
  uploadedBytes: number;
  totalBytes: number;
  percentage: number;
  currentSpeed: number;  // bytes/sec
}
```

## Modified Components

### 1. useUploadOrchestration.ts

Add decision logic for chunked vs single upload:

```typescript
// Modified section
const CHUNK_THRESHOLD = 100 * 1024 * 1024; // 100MB - Cloudflare limit

const processFile = useCallback(async (item: FileQueueItem) => {
  if (item.file.size > CHUNK_THRESHOLD) {
    // Use chunked upload flow
    await processFileChunked(item);
  } else {
    // Use existing single-file flow
    await processFileSingle(item);
  }
}, [processFileChunked, processFileSingle]);
```

### 2. WebSocket Progress Messages

Extend existing progress schema to include upload progress:

```python
# app/schemas/websocket_schemas.py (addition)
class UploadProgressMessage(BaseModel):
    type: Literal["upload_progress"] = "upload_progress"
    session_id: str
    uploaded_chunks: int
    total_chunks: int
    percentage: int
    timestamp: datetime
```

### 3. Progress Emitter

Add upload progress emission capability:

```python
# app/infrastructure/websocket/progress_emitter.py (addition)
def emit_upload_progress(
    self,
    session_id: str,
    uploaded_chunks: int,
    total_chunks: int,
) -> None:
    """Emit upload progress update."""
    percentage = int((uploaded_chunks / total_chunks) * 100)
    coro = self.manager.send_to_task(session_id, {
        "type": "upload_progress",
        "session_id": session_id,
        "uploaded_chunks": uploaded_chunks,
        "total_chunks": total_chunks,
        "percentage": percentage,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # ... schedule on main event loop
```

## Data Flow

### Chunked Upload Flow (files > 100MB)

```
[User drops file > 100MB]
     |
     v
[Frontend: Calculate chunks needed]
     |
     | POST /upload/chunked/session
     | { filename, total_size, total_chunks, language, model }
     v
[Backend: Create UploadSession in DB]
     |
     | Returns { session_id, chunk_size }
     v
[Frontend: Connect WebSocket /ws/tasks/{session_id}]
     |
     v
[Frontend: Upload chunks in sequence]
     |
     +---> [Chunk 0] POST /upload/chunked/{id}/chunk?index=0
     |         |
     |         v
     |     [Backend: Save chunk_0000, update received_chunks]
     |         |
     |         v
     |     [Backend: Emit upload_progress via WebSocket]
     |
     +---> [Chunk 1] POST /upload/chunked/{id}/chunk?index=1
     |     ...
     +---> [Chunk N] POST /upload/chunked/{id}/chunk?index=N
     |
     v
[Frontend: All chunks uploaded]
     |
     | POST /upload/chunked/{session_id}/finalize
     v
[Backend: Assemble chunks into single file]
     |
     | Concatenate chunk_0000 + chunk_0001 + ... + chunk_N
     v
[Backend: Validate assembled file (magic bytes, size)]
     |
     v
[Backend: Trigger transcription pipeline]
     |
     | Create Task entity (same as /speech-to-text)
     | Add background task (process_audio_common)
     v
[Backend: Emit transcription progress via same WebSocket]
     |
     v
[Frontend: Same progress UI as before]
     |
     v
[Transcription Complete]
```

### Decision Flow (Frontend)

```
[File Selected]
     |
     v
[Check file.size]
     |
     +--- < 100MB ---> [Use existing /speech-to-text flow]
     |                      |
     |                      v
     |                 [Single POST, get task_id]
     |                      |
     |                      v
     |                 [WebSocket progress]
     |
     +--- >= 100MB --> [Use chunked upload flow]
                            |
                            v
                       [Create session, get session_id]
                            |
                            v
                       [Upload chunks, session_id = task_id for WS]
                            |
                            v
                       [Finalize, get transcription task_id]
                            |
                            v
                       [WebSocket progress (same as before)]
```

## Endpoint Design

### POST /upload/chunked/session

Create a new upload session.

**Request:**
```json
{
  "filename": "recording.mp4",
  "total_size": 524288000,
  "total_chunks": 10,
  "language": "en",
  "model": "large-v3"
}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "chunk_size": 52428800,
  "expires_at": "2026-01-29T14:30:00Z"
}
```

### POST /upload/chunked/{session_id}/chunk

Upload a single chunk.

**Query Parameters:**
- `index` (int, required): Zero-based chunk index

**Request:**
- Content-Type: application/octet-stream
- Body: Raw chunk bytes

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "chunk_index": 3,
  "received_chunks": 4,
  "total_chunks": 10,
  "status": "uploading"
}
```

### POST /upload/chunked/{session_id}/finalize

Assemble chunks and trigger transcription.

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "processing",
  "message": "File assembled, transcription started"
}
```

### GET /upload/chunked/{session_id}/status

Check upload status (for resume after reconnect).

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "uploading",
  "received_chunks": 4,
  "total_chunks": 10,
  "missing_chunks": [4, 5, 6, 7, 8, 9],
  "expires_at": "2026-01-29T14:30:00Z"
}
```

### DELETE /upload/chunked/{session_id}/abort

Cancel upload and cleanup.

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "aborted",
  "message": "Upload cancelled, chunks deleted"
}
```

## Integration Points

### With Existing WebSocket Infrastructure

The chunked upload system reuses the existing WebSocket infrastructure:

| Component | Reused? | How |
|-----------|---------|-----|
| ConnectionManager | YES | Session ID used as task_id for connection |
| Progress Emitter | EXTENDED | New emit_upload_progress method |
| WebSocket endpoint | YES | /ws/tasks/{session_id} works unchanged |
| Message buffering | YES | Handles race condition of late WS connect |

### With Existing Transcription Pipeline

After assembly, the finalize endpoint reuses the existing pipeline:

```python
# In finalize endpoint
async def finalize_upload(session_id: str):
    # 1. Assemble chunks
    assembled_path = assemble_chunks(session_id)

    # 2. Load audio (same as audio_api.py)
    audio = process_audio_file(assembled_path)

    # 3. Create Task (same entity as /speech-to-text)
    task = DomainTask(
        uuid=str(uuid4()),
        status=TaskStatus.processing,
        file_name=session.filename,
        audio_duration=get_audio_duration(audio),
        language=session.language,
        # ... same fields
    )

    # 4. Schedule background processing (same function)
    background_tasks.add_task(process_audio_common, audio_params)

    return {"task_id": task.uuid, "status": "processing"}
```

### With Existing FileService

Extend FileService with chunk-specific methods:

```python
# app/services/file_service.py (additions)
class FileService:
    # ... existing methods ...

    @staticmethod
    def save_chunk(session_id: str, chunk_index: int, chunk_data: bytes) -> Path:
        """Save a single chunk to session directory."""
        session_dir = UPLOAD_DIR / "chunked" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = session_dir / f"chunk_{chunk_index:04d}"
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)
        return chunk_path

    @staticmethod
    def assemble_chunks(session_id: str, total_chunks: int, output_filename: str) -> Path:
        """Concatenate all chunks into final file."""
        session_dir = UPLOAD_DIR / "chunked" / session_id
        output_path = UPLOAD_DIR / f"{session_id}_{output_filename}"

        with open(output_path, "wb") as output:
            for i in range(total_chunks):
                chunk_path = session_dir / f"chunk_{i:04d}"
                with open(chunk_path, "rb") as chunk:
                    shutil.copyfileobj(chunk, output)

        # Cleanup chunks after assembly
        shutil.rmtree(session_dir)

        return output_path
```

## Build Order

Suggested implementation sequence based on dependencies:

### Phase 1: Backend Foundation
1. **UploadSession database model** - Table for tracking sessions
2. **Session repository** - CRUD operations for sessions
3. **Chunk storage utility** - FileService extensions

### Phase 2: Core Endpoints
4. **POST /session** - Create session endpoint
5. **POST /chunk** - Chunk upload endpoint
6. **Assembly service** - Chunk concatenation logic
7. **POST /finalize** - Assembly + transcription trigger

### Phase 3: Progress & Monitoring
8. **Upload progress emission** - WebSocket integration
9. **GET /status** - Session status endpoint
10. **DELETE /abort** - Cleanup endpoint

### Phase 4: Frontend Integration
11. **Chunked upload service** - API client functions
12. **File slicer utility** - Split file into chunks
13. **Upload orchestration update** - Decision logic (chunked vs single)
14. **Progress UI integration** - Show chunk progress

### Phase 5: Resilience
15. **Retry logic** - Chunk retry on failure
16. **Resume logic** - Check status, upload missing chunks
17. **Session cleanup scheduler** - APScheduler job for expired sessions

### Dependency Graph

```
[Database Model] ──> [Repository] ──> [Create Session Endpoint]
                                              |
                                              v
[FileService Extensions] ──────────> [Chunk Upload Endpoint]
                                              |
                                              v
[Assembly Service] ──────────────────> [Finalize Endpoint]
                                              |
                           ┌──────────────────┴──────────────────┐
                           v                                     v
             [Progress Emission]                    [Existing Transcription]
                    |                                            |
                    v                                            v
             [Frontend Chunked Service]              [Same WebSocket Progress]
                    |
                    v
             [Orchestration Update]
```

## Error Handling

### Chunk Upload Failures

```typescript
// Frontend retry logic
async function uploadChunkWithRetry(
  sessionId: string,
  chunkIndex: number,
  chunk: Blob,
  maxRetries = 3
): Promise<void> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      await uploadChunk(sessionId, chunkIndex, chunk);
      return;
    } catch (error) {
      if (attempt === maxRetries - 1) throw error;
      await sleep(1000 * Math.pow(2, attempt)); // Exponential backoff
    }
  }
}
```

### Session Expiry

Backend cleanup job removes expired sessions:

```python
async def cleanup_expired_sessions():
    """Remove sessions and chunks that have expired."""
    expired_sessions = session_repo.get_expired()
    for session in expired_sessions:
        session_dir = UPLOAD_DIR / "chunked" / session.id
        if session_dir.exists():
            shutil.rmtree(session_dir)
        session_repo.delete(session.id)
```

### Assembly Validation

After assembly, validate before processing:

```python
def validate_assembled_file(file_path: Path, expected_size: int) -> None:
    """Validate assembled file matches expectations."""
    actual_size = file_path.stat().st_size
    if actual_size != expected_size:
        raise ValidationError(f"Size mismatch: expected {expected_size}, got {actual_size}")

    # Validate magic bytes
    is_valid, msg, detected = validate_magic_bytes(file_path, file_path.suffix)
    if not is_valid:
        raise ValidationError(f"Invalid file format: {msg}")
```

## Small Files (No Chunking)

For files under 100MB, the existing flow remains unchanged:

```typescript
// Frontend decision
if (file.size < CHUNK_THRESHOLD) {
  // Use existing startTranscription() from transcriptionApi.ts
  const result = await startTranscription({ file, language, model });
  // Returns { identifier, message } - task_id for WebSocket
}
```

The existing `/speech-to-text` endpoint handles:
- Multipart form upload
- File validation
- Task creation
- Background processing
- WebSocket progress

No changes needed to this flow.

## Sources

### Official Documentation
- [FastAPI Request Files](https://fastapi.tiangolo.com/tutorial/request-files/) - File upload patterns
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) - WebSocket integration
- [streaming-form-data](https://streaming-form-data.readthedocs.io/en/latest/) - Streaming parser

### Chunked Upload Patterns
- [Chunked File Uploads: FastApi & Nodejs Guide](https://arnabgupta.hashnode.dev/mastering-chunked-file-uploads-with-fastapi-and-nodejs-a-step-by-step-guide) - Implementation patterns
- [fast-chunk-upload GitHub](https://github.com/p513817/fast-chunk-upload) - FastAPI chunked upload example
- [FastAPI Discussions #9828](https://github.com/fastapi/fastapi/discussions/9828) - Large file upload patterns

### Resumable Upload Protocols
- [tus.io Protocol](https://tus.io/protocols/resumable-upload) - Resumable upload standard (reference)
- [Uppy Tus Documentation](https://uppy.io/docs/tus/) - Client-side implementation patterns

### React Integration
- [Uppy React Documentation](https://uppy.io/docs/react/) - React file upload patterns

---
*Architecture research for: Chunked uploads integration*
*Researched: 2026-01-29*
