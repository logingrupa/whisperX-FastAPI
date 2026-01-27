"""Progress emission service for bridging sync background tasks to WebSocket clients."""

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core.logging import logger
from app.schemas import TaskProgressStage

if TYPE_CHECKING:
    from app.infrastructure.websocket.connection_manager import ConnectionManager


class ProgressEmitter:
    """
    Emits progress updates from synchronous background tasks to WebSocket clients.

    Background tasks run in a thread pool without an event loop.
    This service bridges that gap by creating a temporary event loop for emission.
    """

    def __init__(self, connection_manager: "ConnectionManager") -> None:
        self.manager = connection_manager

    def emit_progress(
        self,
        task_id: str,
        stage: TaskProgressStage,
        percentage: int,
        message: str = "",
    ) -> None:
        """
        Emit progress update from sync code (background tasks run in thread pool).

        Args:
            task_id: The task identifier
            stage: Current processing stage
            percentage: Progress percentage (0-100)
            message: Optional status message
        """
        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self.manager.send_to_task(task_id, {
                        "type": "progress",
                        "task_id": task_id,
                        "stage": stage.value,
                        "percentage": percentage,
                        "message": message,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                )
            finally:
                loop.close()
        except Exception as e:
            # Don't let WebSocket errors crash the background task
            logger.warning(
                "Failed to emit progress for task %s: %s",
                task_id,
                str(e)
            )

    def emit_error(
        self,
        task_id: str,
        error_code: str,
        user_message: str,
        technical_detail: str | None = None,
    ) -> None:
        """
        Emit error message from sync code.

        Args:
            task_id: The task identifier
            error_code: Error code for programmatic handling
            user_message: User-friendly error message
            technical_detail: Optional technical details for debugging
        """
        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self.manager.send_to_task(task_id, {
                        "type": "error",
                        "task_id": task_id,
                        "error_code": error_code,
                        "user_message": user_message,
                        "technical_detail": technical_detail,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                )
            finally:
                loop.close()
        except Exception as e:
            logger.warning(
                "Failed to emit error for task %s: %s",
                task_id,
                str(e)
            )


# Lazy singleton - initialized on first use
_progress_emitter: ProgressEmitter | None = None


def get_progress_emitter() -> ProgressEmitter:
    """Get or create the progress emitter singleton."""
    global _progress_emitter
    if _progress_emitter is None:
        from app.infrastructure.websocket.connection_manager import connection_manager
        _progress_emitter = ProgressEmitter(connection_manager)
    return _progress_emitter
