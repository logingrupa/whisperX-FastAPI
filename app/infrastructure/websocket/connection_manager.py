"""WebSocket connection manager for task-keyed connections.

This module provides thread-safe management of WebSocket connections,
allowing multiple clients to watch the same task and receive real-time
progress updates. Designed for single-process deployment.

Includes message buffering to handle race conditions where progress
updates are emitted before WebSocket clients connect.
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.schemas.websocket_schemas import HeartbeatMessage

logger = logging.getLogger(__name__)

# Maximum number of messages to buffer per task
MAX_BUFFER_SIZE = 20


class ConnectionManager:
    """Manages WebSocket connections indexed by task_id.

    Provides thread-safe connection tracking and message broadcasting
    for real-time task progress updates. Uses asyncio.Lock for safe
    concurrent access from async handlers and background tasks.

    Includes message buffering to replay missed progress updates when
    a WebSocket client connects after processing has already started.

    Attributes:
        active_connections: Dict mapping task_id to list of WebSocket connections.
        message_buffer: Dict mapping task_id to deque of buffered messages.
    """

    def __init__(self) -> None:
        """Initialize the ConnectionManager with empty connections dict and lock."""
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.message_buffer: dict[str, deque[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection for a task.

        Also replays any buffered messages that were sent before the
        client connected, solving the race condition between task start
        and WebSocket connection.

        Args:
            task_id: UUID of the task to watch.
            websocket: The WebSocket connection to register.
        """
        await websocket.accept()

        # Get buffered messages before acquiring lock (to minimize lock time)
        buffered_messages: list[dict[str, Any]] = []

        async with self._lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)

            # Grab buffered messages for replay
            if task_id in self.message_buffer:
                buffered_messages = list(self.message_buffer[task_id])
                # Clear buffer after grabbing - messages will be sent to new connection
                del self.message_buffer[task_id]

            logger.info(
                "WebSocket connected for task %s (total connections: %d, replaying %d buffered messages)",
                task_id,
                len(self.active_connections[task_id]),
                len(buffered_messages),
            )

        # Replay buffered messages outside of lock
        for message in buffered_messages:
            try:
                await websocket.send_json(message)
                logger.debug(
                    "Replayed buffered message for task %s: stage=%s",
                    task_id,
                    message.get("stage", "unknown"),
                )
            except Exception as error:
                logger.warning(
                    "Failed to replay buffered message for task %s: %s",
                    task_id,
                    str(error),
                )
                break  # Stop replaying if connection has issues

    async def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from tracking.

        Safely removes the connection from the task's connection list.
        Cleans up empty task entries to prevent memory growth.

        Args:
            task_id: UUID of the task being watched.
            websocket: The WebSocket connection to remove.
        """
        async with self._lock:
            if task_id in self.active_connections:
                try:
                    self.active_connections[task_id].remove(websocket)
                    logger.info(
                        "WebSocket disconnected from task %s (remaining: %d)",
                        task_id,
                        len(self.active_connections[task_id]),
                    )
                    # Clean up empty task entries
                    if not self.active_connections[task_id]:
                        del self.active_connections[task_id]
                        logger.debug("Removed empty connection list for task %s", task_id)
                except ValueError:
                    # Connection already removed
                    logger.debug("Connection already removed for task %s", task_id)

    async def send_to_task(self, task_id: str, message: dict[str, Any]) -> None:
        """Send a JSON message to all connections watching a task.

        If no connections exist, buffers the message for later replay
        when a WebSocket client connects. This handles the race condition
        where progress updates are emitted before the frontend connects.

        Handles connection failures gracefully without affecting other
        connections. Failed connections are logged but not automatically
        cleaned up (cleanup happens on disconnect).

        Args:
            task_id: UUID of the task to broadcast to.
            message: Dictionary to serialize as JSON and send.
        """
        async with self._lock:
            connections = list(self.active_connections.get(task_id, []))

            if not connections:
                # No connections yet - buffer the message for replay
                if task_id not in self.message_buffer:
                    self.message_buffer[task_id] = deque(maxlen=MAX_BUFFER_SIZE)
                self.message_buffer[task_id].append(message)
                logger.info(
                    "Buffered message for task %s (stage=%s, buffer size=%d)",
                    task_id,
                    message.get("stage", "unknown"),
                    len(self.message_buffer[task_id]),
                )
                return

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as error:
                logger.warning(
                    "Failed to send message to connection for task %s: %s",
                    task_id,
                    str(error),
                )

    async def send_heartbeat(self, task_id: str) -> None:
        """Send a heartbeat message to all connections watching a task.

        Heartbeats are sent every 30 seconds to prevent proxy timeouts
        during long-running transcription operations.

        Args:
            task_id: UUID of the task to send heartbeat to.
        """
        heartbeat = HeartbeatMessage(timestamp=datetime.now(timezone.utc))
        await self.send_to_task(task_id, heartbeat.model_dump(mode="json"))

    def get_connection_count(self, task_id: str) -> int:
        """Return the number of active connections for a task.

        This is a synchronous method for quick status checks.
        Does not acquire lock for read-only access to avoid blocking.

        Args:
            task_id: UUID of the task to check.

        Returns:
            Number of active WebSocket connections for the task.
        """
        return len(self.active_connections.get(task_id, []))

    async def clear_buffer(self, task_id: str) -> None:
        """Clear buffered messages for a task.

        Called when a task completes without any WebSocket connections
        to prevent memory leaks from orphaned buffers.

        Args:
            task_id: UUID of the task to clear buffer for.
        """
        async with self._lock:
            if task_id in self.message_buffer:
                del self.message_buffer[task_id]
                logger.debug("Cleared message buffer for task %s", task_id)


# Module-level singleton for application-wide use
connection_manager = ConnectionManager()
