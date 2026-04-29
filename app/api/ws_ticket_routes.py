r"""POST /api/ws/ticket — issues a 60-second single-use WS ticket (MID-06).

The browser obtains a one-shot ticket via this authenticated endpoint, then
opens the WebSocket as ``/ws/tasks/{task_id}?ticket=<token>``. Cloudflare
strips ``Sec-WebSocket-Protocol`` (CONTEXT §93), so subprotocol auth is not
viable — the ticket is the locked path.

Locked rules
------------
* DRT  — auth resolved via shared ``Depends(get_authenticated_user)``;
         repository via shared ``Depends(get_task_repository)``; ticket
         service via singleton container provider.
* SRP  — route does HTTP only; ``WsTicketService`` owns ticket lifecycle;
         ``ITaskRepository`` owns persistence.
* /tiger-style — flat early-returns; cross-user task → opaque 404
         (NEVER 403 — no enumeration of foreign tasks, T-13-24); ticket
         value never logged.
* No nested-if — ``grep -cE "^\s+if .*\bif\b"`` returns 0.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.constants import CONTAINER_NOT_INITIALIZED_ERROR
from app.api.dependencies import (
    get_authenticated_user,
    get_task_repository,
)
from app.api.schemas.ws_ticket_schemas import TicketRequest, TicketResponse
from app.domain.entities.user import User
from app.domain.repositories.task_repository import ITaskRepository
from app.services.ws_ticket_service import WsTicketService

logger = logging.getLogger(__name__)

ws_ticket_router = APIRouter(prefix="/api/ws", tags=["WebSocket"])


def get_ws_ticket_service() -> WsTicketService:
    """Provide the singleton ``WsTicketService`` from the global container.

    Lives next to the route (rather than in ``app.api.dependencies``) because
    no other module needs it — Plan 13-09 may relocate this once
    ``websocket_api.py`` also depends on it via FastAPI ``Depends`` instead
    of a direct container reach-in.
    """
    # Imported lazily so test suites can monkey-patch ``dependencies._container``
    # without import-cycle hassle.
    from app.api import dependencies

    if dependencies._container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    return dependencies._container.ws_ticket_service()


@ws_ticket_router.post(
    "/ticket",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_ticket(
    body: TicketRequest,
    user: User = Depends(get_authenticated_user),
    repository: ITaskRepository = Depends(get_task_repository),
    ticket_service: WsTicketService = Depends(get_ws_ticket_service),
) -> TicketResponse:
    """Issue a single-use 60-second WS ticket for the caller's own task.

    Cross-user task ids return ``404`` with the same opaque body as
    "task not found" — no enumeration of foreign tasks (T-13-24, MID-07).

    Note (Plan 13-07 follow-up): ``get_task_repository`` is the un-scoped
    helper. The manual ``task.user_id != user.id`` check below delivers
    MID-07 mitigation today; Plan 13-09 will swap to
    ``get_scoped_task_repository`` and the manual check becomes
    defence-in-depth.
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
