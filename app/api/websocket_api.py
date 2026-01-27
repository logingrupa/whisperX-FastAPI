"""WebSocket API endpoint for real-time task progress updates.

This module provides the WebSocket endpoint that clients connect to
for receiving real-time progress updates during transcription operations.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.infrastructure.websocket import connection_manager
from app.schemas.websocket_schemas import HeartbeatMessage

logger = logging.getLogger(__name__)

websocket_router = APIRouter(tags=["WebSocket"])

HEARTBEAT_INTERVAL_SECONDS = 30


@websocket_router.websocket("/ws/tasks/{task_id}")
async def websocket_task_progress(websocket: WebSocket, task_id: str) -> None:
    """WebSocket endpoint for receiving task progress updates.

    Clients connect to this endpoint to receive real-time progress updates
    for a specific task. The connection sends:
    - Progress messages when task stage/percentage changes
    - Heartbeat messages every 30 seconds to prevent proxy timeouts
    - Error messages if task processing fails

    Clients can send:
    - ping messages (type="ping") to receive pong responses

    Args:
        websocket: The WebSocket connection.
        task_id: UUID of the task to watch.
    """
    await connection_manager.connect(task_id, websocket)
    logger.info("WebSocket connection established for task %s", task_id)

    async def send_heartbeat_loop() -> None:
        """Send heartbeat messages every 30 seconds."""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                heartbeat = HeartbeatMessage(timestamp=datetime.now(timezone.utc))
                await websocket.send_json(heartbeat.model_dump(mode="json"))
                logger.debug("Heartbeat sent for task %s", task_id)
            except Exception as error:
                logger.debug(
                    "Heartbeat loop ending for task %s: %s",
                    task_id,
                    str(error),
                )
                break

    heartbeat_task = asyncio.create_task(send_heartbeat_loop())

    try:
        while True:
            # Receive and handle client messages
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                logger.debug("Pong sent for task %s", task_id)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for task %s", task_id)
    except Exception as error:
        logger.warning(
            "WebSocket error for task %s: %s",
            task_id,
            str(error),
        )
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await connection_manager.disconnect(task_id, websocket)
        logger.debug("WebSocket cleanup complete for task %s", task_id)
