"""Billing routes — Stripe checkout stub (BILL-05; UI lands in Phase 15).

Phase 19-07 SPLIT: the Stripe webhook moved to
``app.api.billing_webhook_routes`` (auth-free, CSRF-free; Stripe-Signature
HMAC schema check at the route level). This module retains ONLY the
authenticated, CSRF-protected ``/billing/checkout`` stub.

Why split: FastAPI does NOT support per-route dependency removal. Adding
router-level ``Depends(csrf_protected)`` here would 403 the webhook (no
``X-CSRF-Token`` from Stripe). Two routers, one prefix.

BILL-07: ``stripe`` is imported at module-load only — ZERO runtime
``stripe.*`` calls in v1.2.

Constraints honoured:
    DRY  — authenticated_user + csrf_protected applied router-level
           (single resolution point).
    SRP  — route returns 501; no business logic; no DB writes; no
           external API calls.
    No nested-if (verifier-checked).
"""

from __future__ import annotations

import logging

import stripe  # noqa: F401  # BILL-07 — module-load import only; no runtime calls

from fastapi import APIRouter, Depends, status

from app.api.dependencies import authenticated_user, csrf_protected
from app.api.schemas.billing_schemas import CheckoutRequest, StubResponse
from app.domain.entities.user import User

logger = logging.getLogger(__name__)

billing_router = APIRouter(
    prefix="/billing",
    tags=["Billing"],
    dependencies=[Depends(csrf_protected)],
)


@billing_router.post(
    "/checkout",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=StubResponse,
)
async def checkout_stub(
    body: CheckoutRequest,
    user: User = Depends(authenticated_user),
) -> StubResponse:
    """Return 501 stub — actual Stripe Checkout in v1.3."""
    logger.info(
        "Billing checkout stub invoked user_id=%s plan=%s",
        user.id, body.plan,
    )
    return StubResponse()
