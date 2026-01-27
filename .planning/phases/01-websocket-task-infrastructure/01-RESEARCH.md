# Phase 1: WebSocket & Task Infrastructure - Research

**Researched:** 2026-01-27
**Domain:** FastAPI WebSocket real-time progress updates
**Confidence:** HIGH

## Summary

This phase implements WebSocket infrastructure for real-time task progress updates in a FastAPI application with long-running transcription operations (5-30 minutes). The research covers WebSocket endpoint implementation, connection management, heartbeat mechanisms to prevent proxy timeouts, and fallback polling strategies.

FastAPI's WebSocket support is built on Starlette and provides straightforward async WebSocket handling. The standard pattern uses a ConnectionManager class to track active connections and broadcast messages. For this single-process application, an in-memory connection manager is sufficient. The existing `BackgroundTasks` processing flow needs modification to emit progress updates at key stages.

**Primary recommendation:** Implement a task-keyed ConnectionManager with 30-second server-initiated heartbeats, JSON message format for progress updates, and a polling endpoint that queries the same progress state for fallback scenarios.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.128.0 (installed) | WebSocket endpoint support | Already in use, built-in WebSocket decorator |
| Starlette | (via FastAPI) | Underlying WebSocket implementation | FastAPI's foundation, provides WebSocket class |
| uvicorn | 0.40.0 (installed) | ASGI server with WebSocket support | Already in use, configurable ping/timeout settings |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| websockets | latest | Protocol implementation | Uvicorn's default WebSocket protocol handler |
| pydantic | (installed) | Message schema validation | Validate progress update JSON structure |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-memory ConnectionManager | Redis pub/sub | Only needed for multi-process/multi-worker deployment |
| fastapi-websocket-pubsub | Custom implementation | Adds complexity; overkill for single-process |
| encode/broadcaster | Custom implementation | Archived (Aug 2025), API marked unstable |

**Installation:**
No additional packages required. FastAPI and uvicorn already provide WebSocket support.

## Architecture Patterns

### Recommended Project Structure
```
app/
├── api/
│   └── websocket_api.py          # WebSocket endpoint and route
├── infrastructure/
│   └── websocket/
│       ├── __init__.py
│       ├── connection_manager.py # ConnectionManager class
│       └── progress_emitter.py   # Progress emission service
├── domain/
│   └── entities/
│       └── task_progress.py      # Progress value object (optional)
└── schemas/
    └── websocket_schemas.py      # Pydantic models for WS messages
```

### Pattern 1: ConnectionManager with Task-Keyed Connections

**What:** A manager class that tracks WebSocket connections indexed by task_id, enabling targeted message delivery to clients watching specific tasks.

**When to use:** When clients need to receive updates for specific tasks they initiated, not broadcasts.

**Example:**
```python
# Source: FastAPI official docs + customization for task-specific routing
from fastapi import WebSocket
from typing import Dict
import asyncio

class ConnectionManager:
    def __init__(self):
        # Map: task_id -> list of WebSocket connections
        self.active_connections: Dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)

    async def disconnect(self, task_id: str, websocket: WebSocket):
        async with self._lock:
            if task_id in self.active_connections:
                self.active_connections[task_id].remove(websocket)
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]

    async def send_to_task(self, task_id: str, message: dict):
        """Send progress update to all connections watching a task."""
        async with self._lock:
            connections = self.active_connections.get(task_id, [])
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection may have closed; cleanup handled elsewhere
                pass
```

### Pattern 2: WebSocket Endpoint with Heartbeat

**What:** A WebSocket endpoint that handles connection lifecycle and sends periodic heartbeats to prevent proxy timeouts.

**When to use:** Always for long-running operations where idle connections may be terminated.

**Example:**
```python
# Source: FastAPI docs + Uvicorn timeout considerations
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio

app = FastAPI()
manager = ConnectionManager()

@app.websocket("/ws/tasks/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await manager.connect(task_id, websocket)

    async def send_heartbeat():
        """Send heartbeat every 30 seconds to keep connection alive."""
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "heartbeat", "timestamp": time.time()})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(send_heartbeat())

    try:
        while True:
            # Receive messages from client (e.g., for client-initiated pings)
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(task_id, websocket)
```

### Pattern 3: Progress Emission from Background Tasks

**What:** A mechanism to emit progress updates from synchronous background tasks to WebSocket clients.

**When to use:** When background processing needs to communicate stage transitions.

**Example:**
```python
# Source: FastAPI background tasks pattern + asyncio event loop bridging
import asyncio
from typing import Callable

class ProgressEmitter:
    def __init__(self, manager: ConnectionManager):
        self.manager = manager

    def emit_progress(self, task_id: str, stage: str, percentage: int, message: str = ""):
        """Emit progress from sync code (background tasks run in thread pool)."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                self.manager.send_to_task(task_id, {
                    "type": "progress",
                    "task_id": task_id,
                    "stage": stage,
                    "percentage": percentage,
                    "message": message,
                    "timestamp": time.time()
                })
            )
        finally:
            loop.close()
```

### Anti-Patterns to Avoid

- **Global broadcast for task progress:** Don't send all task updates to all connected clients. Use task-keyed connections to target only interested clients.

- **Blocking the event loop:** Background tasks run in a thread pool. Don't try to await async operations directly. Use `asyncio.run_coroutine_threadsafe()` or create a new event loop.

- **No heartbeat:** Relying solely on WebSocket protocol-level pings. Uvicorn's default 20s ping may not be visible to all proxies. Application-level heartbeats are more reliable.

- **Percentage estimation based on time:** Don't estimate completion percentage from elapsed time. Transcription duration varies wildly based on audio content, hardware, and model.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket ping/pong | Custom ping implementation | Uvicorn's `--ws-ping-interval` + app heartbeat | Protocol-level and app-level serve different purposes |
| Connection state tracking | Manual state flags | Starlette's WebSocket state handling | Already handles disconnection detection |
| JSON serialization | Manual dict to string | `websocket.send_json()` / Pydantic | Starlette provides JSON methods |
| Async lock | `threading.Lock` | `asyncio.Lock` | ConnectionManager is async; use appropriate primitives |

**Key insight:** FastAPI/Starlette already provides robust WebSocket primitives. The complexity is in integrating with background task progress emission, not in WebSocket handling itself.

## Common Pitfalls

### Pitfall 1: Thread Safety in ConnectionManager

**What goes wrong:** Background tasks run in a thread pool while WebSocket handling is async. Concurrent access to connection lists causes race conditions.

**Why it happens:** FastAPI's `BackgroundTasks` uses `run_in_executor`, creating thread concurrency with async code.

**How to avoid:** Use `asyncio.Lock` for connection management. Use thread-safe communication (queue or event loop bridging) for progress emission.

**Warning signs:** Intermittent KeyError when accessing connections, connections appearing to drop randomly.

### Pitfall 2: Proxy Timeout During Long Operations

**What goes wrong:** Load balancers/reverse proxies (nginx, CloudFlare, AWS ALB) close idle WebSocket connections after 30-120 seconds.

**Why it happens:** HTTP/1.1 infrastructure assumes short-lived connections. No traffic = dead connection assumption.

**How to avoid:** Send heartbeat messages every 30 seconds (well under typical 60s timeout). The CONTEXT.md specifies 30-second intervals.

**Warning signs:** Connections drop after ~1 minute of silence during transcription stage.

### Pitfall 3: Event Loop Mismatch

**What goes wrong:** Attempting to call `await` from synchronous background task code raises "no running event loop" error.

**Why it happens:** Background tasks execute in thread pool threads, which don't have an event loop.

**How to avoid:** Use `asyncio.run_coroutine_threadsafe(coro, loop)` passing the main event loop, or create a temporary event loop for emission.

**Warning signs:** `RuntimeError: no running event loop` when emitting progress.

### Pitfall 4: Stale Database Session in Progress Polling

**What goes wrong:** Polling endpoint returns outdated progress because SQLAlchemy session caches old data.

**Why it happens:** SQLAlchemy's unit-of-work pattern caches loaded objects. Progress updates from background tasks use different sessions.

**How to avoid:** Call `session.refresh(task)` before reading progress, or use a fresh session per poll request.

**Warning signs:** Polling shows "processing" long after task completed.

### Pitfall 5: WebSocket Exception vs HTTP Exception

**What goes wrong:** Using `raise HTTPException` in WebSocket endpoint handlers.

**Why it happens:** Habit from HTTP endpoint development.

**How to avoid:** Use `raise WebSocketException(code=...)` with appropriate WebSocket close codes (e.g., 1008 for policy violation).

**Warning signs:** Client receives confusing error responses instead of clean WebSocket close.

## Code Examples

Verified patterns from official sources:

### WebSocket Endpoint with Dependencies
```python
# Source: FastAPI official docs - https://fastapi.tiangolo.com/advanced/websockets/
from typing import Annotated
from fastapi import Cookie, Depends, Query, WebSocketException, status

async def verify_token(
    websocket: WebSocket,
    token: Annotated[str | None, Query()] = None,
):
    if token is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return token

@app.websocket("/ws/tasks/{task_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    task_id: str,
    token: Annotated[str, Depends(verify_token)],
):
    await websocket.accept()
    # ... handle connection
```

### Sending Different Data Types
```python
# Source: Starlette WebSocket docs - https://www.starlette.io/websockets/
# Text
await websocket.send_text("Hello")

# JSON (uses text frames by default)
await websocket.send_json({"type": "progress", "percentage": 50})

# Binary
await websocket.send_bytes(b"\x00\x01\x02")

# Close with code
await websocket.close(code=1000, reason="Task completed")
```

### Async Iterator for Receiving
```python
# Source: Starlette WebSocket docs
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    async for message in websocket.iter_json():
        if message.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
```

### Progress Message Schema (Recommended)
```python
# Based on NVIDIA AIQ Toolkit pattern + project requirements
from pydantic import BaseModel
from enum import Enum
from datetime import datetime

class ProgressStage(str, Enum):
    UPLOADING = "uploading"
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    ALIGNING = "aligning"
    DIARIZING = "diarizing"
    COMPLETE = "complete"

class ProgressMessage(BaseModel):
    type: str = "progress"
    task_id: str
    stage: ProgressStage
    percentage: int  # 0-100, whole numbers per CONTEXT.md discretion
    message: str | None = None  # Optional sub-description
    timestamp: datetime

class ErrorMessage(BaseModel):
    type: str = "error"
    task_id: str
    error_code: str
    user_message: str
    technical_detail: str | None = None
    timestamp: datetime

class HeartbeatMessage(BaseModel):
    type: str = "heartbeat"
    timestamp: datetime
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Server-Sent Events | WebSockets | Long established | Bidirectional, better for interactive apps |
| `encode/broadcaster` for scaling | `fastapi-websocket-pubsub` or custom Redis | Aug 2025 (archived) | Need alternative for multi-process |
| Gunicorn workers | Uvicorn workers | FastAPI standard | Single-process simpler, multi-process needs pub/sub |

**Deprecated/outdated:**
- `encode/broadcaster`: Archived August 2025, API marked unstable. Use `fastapi-websocket-pubsub` if scaling needed.

## Open Questions

Things that couldn't be fully resolved:

1. **Percentage calculation granularity**
   - What we know: Whole numbers preferred (CONTEXT.md leaves to discretion)
   - What's unclear: How to calculate percentage within each stage (transcription progress is opaque)
   - Recommendation: Use stage-based progress (0-100 mapped to stages: Transcribing=20-50%, Aligning=50-70%, Diarizing=70-95%, Complete=100%)

2. **Reconnection catch-up behavior**
   - What we know: Client should reconnect with exponential backoff (CONTEXT.md)
   - What's unclear: Whether to replay missed progress or just send current state
   - Recommendation: Send current state only. Keep it simple. Client can poll for current state on reconnect.

3. **Multi-worker deployment future**
   - What we know: Current app is single-process
   - What's unclear: Future scaling requirements
   - Recommendation: Design ConnectionManager interface to be swappable. Don't over-engineer now, but don't preclude Redis pub/sub later.

## Sources

### Primary (HIGH confidence)
- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/) - Core patterns, ConnectionManager, dependencies
- [Starlette WebSocket Documentation](https://www.starlette.io/websockets/) - send_json, iter_json, close codes
- [Uvicorn Settings](https://www.uvicorn.org/settings/) - ws-ping-interval, ws-ping-timeout configuration
- [websockets library keepalive docs](https://websockets.readthedocs.io/en/stable/topics/keepalive.html) - Ping/pong mechanism, timeout reasoning

### Secondary (MEDIUM confidence)
- [Better Stack FastAPI WebSockets Guide](https://betterstack.com/community/guides/scaling-python/fastapi-websockets/) - ConnectionManager implementation patterns
- [fastapi-websocket-pubsub PyPI](https://pypi.org/project/fastapi-websocket-pubsub/) - Multi-process scaling option (v1.0.1, June 2025)
- [NVIDIA AIQ Toolkit WebSocket Schema](https://docs.nvidia.com/aiqtoolkit/latest/reference/websockets.html) - Progress message format inspiration

### Tertiary (LOW confidence)
- Medium articles on FastAPI + Redis pub/sub - Community patterns, not officially documented
- Socket.IO fallback patterns - Different ecosystem but useful fallback strategy concepts

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - FastAPI/Starlette WebSocket support is well-documented and stable
- Architecture: HIGH - ConnectionManager pattern is official FastAPI recommendation
- Pitfalls: HIGH - Thread safety and proxy timeout issues are well-documented
- Progress emission integration: MEDIUM - Requires adapting patterns to existing background task flow

**Research date:** 2026-01-27
**Valid until:** 2026-02-27 (30 days - stable domain)

---

## Existing Codebase Integration Notes

### Current Architecture Understanding

The application uses:
- **FastAPI BackgroundTasks** for async processing (`background_tasks.add_task()`)
- **SQLAlchemy** with SQLite for task persistence
- **DDD architecture**: Domain entities, repositories, services
- **Dependency injection** via `dependency-injector` container

### Key Integration Points

1. **Task creation** (`app/api/audio_api.py`):
   - Tasks created with `TaskStatus.processing`
   - `background_tasks.add_task(process_audio_common, audio_params)` queues work

2. **Background processing** (`app/services/whisperx_wrapper_service.py`):
   - `process_audio_common()` is the main processing function
   - Four sequential stages: transcription -> alignment -> diarization -> speaker assignment
   - Repository updates status to `completed` or `failed` at end

3. **Task status enum** (`app/schemas.py`):
   - Currently only: `processing`, `completed`, `failed`
   - Needs extension for granular stages

4. **Database model** (`app/infrastructure/database/models.py`):
   - Task table has no progress fields currently
   - May need `progress_percentage`, `progress_stage` columns for polling fallback

### Recommended Changes (for planner)

1. Add WebSocket endpoint at `/ws/tasks/{task_id}`
2. Create `ConnectionManager` in `app/infrastructure/websocket/`
3. Create `ProgressEmitter` injectable service
4. Modify `process_audio_common()` to call progress emitter between stages
5. Add `TaskProgressStage` enum for granular stages
6. Add progress columns to Task model for polling fallback
7. Create polling endpoint `GET /tasks/{task_id}/progress`
