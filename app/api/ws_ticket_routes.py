r"""POST /api/ws/ticket — issues a 60-second single-use WS ticket (MID-06).

The browser obtains a one-shot ticket via this authenticated endpoint, then
opens the WebSocket as ``/ws/tasks/{task_id}?ticket=<token>``. Cloudflare
strips ``Sec-WebSocket-Protocol`` (CONTEXT §93), so subprotocol auth is not
viable — the ticket is the locked path.

Locked rules
------------
* DRT  — auth resolved via the shared authenticated_user Depends;
         repository via the shared scoped task repo Depends (Plan 19-04
         — scope auto-applied); ticket service via the lru-cached
         singleton in ``app.core.services``.
* SRP  — route does HTTP only; ``WsTicketService`` owns ticket lifecycle;
         ``ITaskRepository`` owns persistence.
* /tiger-style — flat early-returns; cross-user task → opaque 404
         (NEVER 403 — no enumeration of foreign tasks, T-13-24); ticket
         value never logged.
* No nested-if — ``grep -cE "^\s+if .*\bif\b"`` returns 0.

Phase 19-07: dropped the inline ``get_ws_ticket_service`` factory that
reached into ``dependencies._container``; replaced with a direct import
from ``app.core.services``. Router-level ``Depends(csrf_protected)``
applied (POST /api/ws/ticket is state-mutating in the cookie-auth flow).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    authenticated_user,
    csrf_protected,
    get_scoped_task_repository_v2,
)
from app.api.schemas.ws_ticket_schemas import TicketRequest, TicketResponse
from app.core.services import get_ws_ticket_service
from app.domain.entities.user import User
from app.domain.repositories.task_repository import ITaskRepository
from app.services.ws_ticket_service import WsTicketService

logger = logging.getLogger(__name__)

ws_ticket_router = APIRouter(
    prefix="/api/ws",
    tags=["WebSocket"],
    dependencies=[Depends(csrf_protected)],
)


@ws_ticket_router.post(
    "/ticket",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_ticket(
    body: TicketRequest,
    user: User = Depends(authenticated_user),
    repository: ITaskRepository = Depends(get_scoped_task_repository_v2),
    ticket_service: WsTicketService = Depends(get_ws_ticket_service),
) -> TicketResponse:
    """Issue a single-use 60-second WS ticket for the caller's own task.

    Cross-user task ids return ``404`` with the same opaque body as
    "task not found" — no enumeration of foreign tasks (T-13-24, MID-07).

    Plan 13-07: repository is now ``get_scoped_task_repository`` — the
    scoped query already returns None for cross-user task ids, so the
    first ``task is None`` guard catches the cross-user path. The manual
    ``task.user_id != user.id`` check below remains as defence-in-depth
    (catches drift if a task's user_id is mutated post-issue, MID-07).
    """
    task = repository.get_by_id(body.task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    if task.user_id != user.id:
        # Same opaque message — anti-enumeration of foreign tasks (T-13-24).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    token, expires_at = ticket_service.issue(
        user_id=int(user.id), task_id=body.task_id  # type: ignore[arg-type]
    )
    # NEVER log token value (T-13-29) — only event labels.
    logger.info(
        "ws_ticket issued user_id=%s task_id=%s", user.id, body.task_id
    )
    return TicketResponse(ticket=token, expires_at=expires_at)
