"""Pydantic v2 schemas for ``/api/usage`` route (quick-260505-l2w).

Single source of truth for the usage-summary response. Mirrors the style
of ``app/api/schemas/account_schemas.py`` — pure DTO, no business logic,
field allowlist enforces what crosses the wire.

Constraints honoured:
    DRY  — schema defined once; usage_routes.get_usage imports from here.
    SRP  — pure DTO; no SQL, no service-layer state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PlanTier = Literal["free", "trial", "pro", "team"]


class UsageSummaryResponse(BaseModel):
    """GET /api/usage — current rate-limit + trial state for the caller."""

    plan_tier: PlanTier
    trial_started_at: datetime | None = None
    trial_expires_at: datetime | None = Field(
        None,
        description="trial_started_at plus seven days; None when trial_started_at is None",
    )
    hour_count: int = Field(..., ge=0)
    hour_limit: int = Field(..., ge=0)
    daily_minutes_used: float = Field(..., ge=0.0)
    daily_minutes_limit: float = Field(..., ge=0.0)
    window_resets_at: datetime
    day_resets_at: datetime
