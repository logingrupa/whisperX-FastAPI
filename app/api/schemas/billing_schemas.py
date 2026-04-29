"""Pydantic schemas for ``/billing/*`` (Phase 13 stubs; v1.3 fills in).

Both endpoints currently return 501 with ``StubResponse`` — the schemas
are stable so Phase 14/15 frontend can build dashboards against them
without churn when the real Stripe integration lands in v1.3.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    """POST /billing/checkout body (placeholder fields for v1.2)."""

    plan: str = Field(
        ...,
        description="Pro tier identifier (currently 'pro')",
    )


class StubResponse(BaseModel):
    """Generic 501 stub body (BILL-05/06)."""

    detail: str = "Not Implemented"
    status: str = "stub"
    hint: str = "Stripe integration arrives in v1.3"
