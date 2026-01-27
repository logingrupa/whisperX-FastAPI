"""WebSocket infrastructure module for real-time task progress updates."""

from app.infrastructure.websocket.connection_manager import (
    ConnectionManager,
    connection_manager,
)

__all__ = ["ConnectionManager", "connection_manager"]
