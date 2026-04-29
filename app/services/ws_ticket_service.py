"""WS ticket service — 60-second single-use tickets for WebSocket auth (MID-06).

Per CONTEXT §93: in-memory dict with TTL eviction; single-worker scope is
acceptable for v1.2 (the deploy uses a single uvicorn worker). A multi-worker
fan-out would require Redis or a DB-backed store — out of scope.

Tickets are SHA-256-strong random tokens (``secrets.token_urlsafe`` truncated
to ``TICKET_LENGTH``). Each ticket carries the issuing ``user_id`` and the
``task_id`` it was issued against; ``consume`` enforces:

* token exists
* not yet consumed (single-use)
* not expired (``expires_at >= now``)
* ``ticket.task_id == provided task_id`` (cross-task / cross-user mitigation)

Any failure returns ``None`` so the WS handler can close 1008 (Policy
Violation) on a single uniform path.

Locked rules
------------
* DRT — failure modes share the early-return pattern; one ``None`` site.
* SRP — service owns ticket lifecycle only (no HTTP / no WS knowledge).
* /tiger-style — single-use enforced under a Lock; failure modes are flat
  guard clauses; ticket length and TTL are module constants (no magic
  numbers); logger never emits the token value (T-13-29).
* No nested-if — every guard is a top-level ``if`` returning early.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

TICKET_TTL_SECONDS = 60
TICKET_LENGTH = 32


@dataclass
class _Ticket:
    """Internal ticket record. Module-private — never leaves the service."""

    user_id: int
    task_id: str
    expires_at: datetime
    consumed: bool = False


class WsTicketService:
    """In-memory single-use TTL ticket store. Thread-safe via ``threading.Lock``.

    The lock guards both the dict and the per-ticket ``consumed`` flag so
    concurrent ``consume`` calls observe atomic single-use semantics. FastAPI
    runs single-threaded per worker, but ``BackgroundTasks`` and
    ``asyncio.to_thread`` are cheap insurance.
    """

    def __init__(self) -> None:
        self._tickets: dict[str, _Ticket] = {}
        self._lock = threading.Lock()

    def issue(self, *, user_id: int, task_id: str) -> tuple[str, datetime]:
        """Issue a fresh ticket valid for ``TICKET_TTL_SECONDS``.

        Args:
            user_id: Authenticated user id (from ``request.state.user``).
            task_id: UUID of the task the WS will subscribe to.

        Returns:
            Tuple ``(token, expires_at)`` — token is urlsafe and exactly
            ``TICKET_LENGTH`` characters; ``expires_at`` is tz-aware UTC.
        """
        # Best-effort eviction keeps the dict bounded under sustained issue
        # pressure (T-13-28 mitigation).
        self.cleanup_expired()
        # token_urlsafe(24) yields 32 urlsafe chars (4 * ceil(24/3)); slice is
        # defensive against future Python changes that might pad differently.
        token = secrets.token_urlsafe(24)[:TICKET_LENGTH]
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=TICKET_TTL_SECONDS)
        with self._lock:
            self._tickets[token] = _Ticket(
                user_id=user_id, task_id=task_id, expires_at=expires_at
            )
        # NEVER log the token value (T-13-29).
        logger.debug("WsTicket issued user_id=%s task_id=%s", user_id, task_id)
        return token, expires_at

    def consume(self, token: str, task_id: str) -> int | None:
        """Atomically consume a ticket; return ``user_id`` on success, ``None``
        on any failure.

        Failure modes (all return ``None``; caller closes WS with code 1008):

        * token not found
        * ticket already consumed (single-use — T-13-25)
        * ticket expired (TTL exceeded — T-13-26)
        * ticket ``task_id`` mismatches the provided ``task_id`` (cross-task —
          T-13-27 first-line defence; second-line check lives in the WS
          handler)

        Args:
            token: The ticket value from the WS query string.
            task_id: The path-parameter task id the client is subscribing to.

        Returns:
            ``user_id`` if all checks pass; ``None`` otherwise.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            ticket = self._tickets.get(token)
            if ticket is None:
                return None
            if ticket.consumed:
                return None
            if ticket.expires_at < now:
                return None
            if ticket.task_id != task_id:
                return None
            ticket.consumed = True
            user_id = ticket.user_id
        logger.debug("WsTicket consumed user_id=%s task_id=%s", user_id, task_id)
        return user_id

    def cleanup_expired(self) -> int:
        """Best-effort eviction of expired and consumed tickets.

        Returns the count of removed entries. Called automatically on every
        ``issue``; safe to call externally for a periodic sweep.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            stale_keys = [
                key
                for key, ticket in self._tickets.items()
                if ticket.expires_at < now or ticket.consumed
            ]
            for key in stale_keys:
                del self._tickets[key]
        return len(stale_keys)
