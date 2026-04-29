"""Pydantic schemas for ``POST /api/ws/ticket`` (MID-06).

Locked shapes (CONTEXT §93):

* ``TicketRequest`` — caller-supplied ``task_id`` (UUID of the task the WS
  will subscribe to).
* ``TicketResponse`` — ``ticket`` (single-use token) + ``expires_at``
  (tz-aware UTC datetime; client renews if expired).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TicketRequest(BaseModel):
    """Request body for ``POST /api/ws/ticket``."""

    task_id: str = Field(
        ...,
        description="UUID of the task the WebSocket will subscribe to.",
        min_length=1,
    )


class TicketResponse(BaseModel):
    """Response body for ``POST /api/ws/ticket`` (201)."""

    ticket: str = Field(
        ..., description="Single-use 32-char ticket — pass as ?ticket=<token>."
    )
    expires_at: datetime = Field(
        ..., description="Token expiry (UTC, tz-aware). 60 seconds after issue."
    )
