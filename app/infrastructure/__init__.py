"""Infrastructure layer - External integrations and technical concerns."""

from app.infrastructure.websocket import ConnectionManager, connection_manager

__all__ = ["ConnectionManager", "connection_manager"]
