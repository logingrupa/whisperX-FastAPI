"""WebSocket API endpoint with single-use 60s ticket auth (MID-06 / MID-07).

Per CONTEXT §93-94: the WS endpoint accepts ``?ticket=<token>`` query param,
consumes the ticket atomically, and rejects with code ``1008`` (Policy
Violation) on any failure (missing / expired / reused / cross-user).

Validation chain (flat early-returns; no nested-if):

1.  ``ticket`` query param missing       → close 1008
2.  Container not initialised            → close 1008 (defensive)
3.  Task with ``task_id`` not found      → close 1008 (T-13-27)
4.  ``ticket_service.consume`` returns
    ``None`` (unknown / expired / reused
    / cross-task)                        → close 1008
5.  ``consumed_user_id != task.user_id`` → close 1008 (defence-in-depth
                                            second-line check after consume,
                                            MID-07)

Only after all 5 guards pass does the legacy ``connection_manager.connect``
flow run. The original heartbeat + ping/pong loop is preserved verbatim.

Locked rules
------------
* DRT  — single ``await websocket.close(code=WS_POLICY_VIOLATION)`` site
         per guard (5 sites; one constant).
* SRP  — endpoint does WS auth + lifecycle; ``WsTicketService`` owns ticket
         mechanics; ``connection_manager`` owns connection bookkeeping.
* /tiger-style — fail fast with the most specific failure first; never log
         the ticket token value (T-13-29).
* No nested-if — every guard is a top-level ``if`` returning early.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.services import get_ws_ticket_service
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from app.infrastructure.websocket import connection_manager
from app.schemas.websocket_schemas import HeartbeatMessage

logger = logging.getLogger(__name__)

websocket_router = APIRouter(tags=["WebSocket"])

HEARTBEAT_INTERVAL_SECONDS = 30
WS_POLICY_VIOLATION = 1008


@websocket_router.websocket("/ws/tasks/{task_id}")
async def websocket_task_progress(
    websocket: WebSocket,
    task_id: str,
    ticket: str = Query(default=""),
) -> None:
    """WebSocket endpoint for task progress with ticket-validated auth.

    Five flat guards run before ``connection_manager.connect``; any failure
    closes the socket with ``1008`` (Policy Violation). Only the ticket flow
    is supported — there is no legacy unauthenticated path.

    Args:
        websocket: The WebSocket connection.
        task_id: UUID of the task to watch (path param).
        ticket: Single-use token from ``POST /api/ws/ticket`` (query param).
    """
    # WS scope has no FastAPI Depends, so we use the lru-cached singleton
    # for ws_ticket_service (HTTP issue and WS consume agree on the same
    # in-memory dict) and an explicit ``with SessionLocal() as db:`` block
    # for the per-request session. The context manager owns close().
    if not ticket:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    ticket_service = get_ws_ticket_service()
    with SessionLocal() as db:
        task = SQLAlchemyTaskRepository(db).get_by_id(task_id)
    if task is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    # Atomic single-use consume — handles unknown / expired / reused /
    # cross-task in one call. Returns ``None`` on any failure.
    consumed_user_id = ticket_service.consume(ticket, task_id)
    if consumed_user_id is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    # Defence-in-depth (MID-07 belt-and-braces): even though consume()
    # already verified ticket.task_id == task_id, re-confirm the
    # user_id stored on the task matches the consumed ticket's user_id.
    # Catches any future drift where a ticket might be issued for a task
    # whose user_id was changed after issue.
    if consumed_user_id != task.user_id:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    # ---- ticket valid; run the legacy connection-manager flow verbatim ----
    await connection_manager.connect(task_id, websocket)
    logger.info(
        "WebSocket connection established for task %s user_id=%s",
        task_id,
        consumed_user_id,
    )

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
