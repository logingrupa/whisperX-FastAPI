"""WebSocket connection manager for task-keyed connections.

This module provides thread-safe management of WebSocket connections,
allowing multiple clients to watch the same task and receive real-time
progress updates. Designed for single-process deployment.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.schemas.websocket_schemas import HeartbeatMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections indexed by task_id.

    Provides thread-safe connection tracking and message broadcasting
    for real-time task progress updates. Uses asyncio.Lock for safe
    concurrent access from async handlers and background tasks.

    Attributes:
        active_connections: Dict mapping task_id to list of WebSocket connections.
    """

    def __init__(self) -> None:
        """Initialize the ConnectionManager with empty connections dict and lock."""
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection for a task.

        Args:
            task_id: UUID of the task to watch.
            websocket: The WebSocket connection to register.
        """
        await websocket.accept()
        async with self._lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)
            logger.info(
                "WebSocket connected for task %s (total connections: %d)",
                task_id,
                len(self.active_connections[task_id]),
            )

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
            logger.debug("No active connections for task %s", task_id)
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


# Module-level singleton for application-wide use
connection_manager = ConnectionManager()
