"""Billing routes — Stripe stubs (BILL-05/06; UI lands in Phase 15).

BILL-07: imports ``stripe`` at module-load — ZERO runtime ``stripe.*`` calls
in v1.2. The package is imported only so the dependency tree resolves
identically to the v1.3 build (when real Stripe API calls arrive).

Both endpoints return 501 with a placeholder ``StubResponse``. The
``/billing/webhook`` endpoint additionally validates the
``Stripe-Signature`` header SCHEMA (regex shape only — NOT HMAC) so
malformed/spam traffic is rejected with 400 before reaching the 501
branch. Full HMAC signature verification arrives in v1.3 alongside real
``stripe.Webhook.construct_event(...)``.

Constraints honoured:
    DRY  — get_authenticated_user dependency reused on /checkout (single
           resolution point set by DualAuthMiddleware).
    SRP  — routes return 501; no business logic; no DB writes; no
           external API calls.
    No nested-if (verifier-checked).
"""

from __future__ import annotations

import logging
import re

import stripe  # noqa: F401  # BILL-07 — module-load import only; no runtime calls

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import get_authenticated_user
from app.api.schemas.billing_schemas import CheckoutRequest, StubResponse
from app.domain.entities.user import User

logger = logging.getLogger(__name__)

billing_router = APIRouter(prefix="/billing", tags=["Billing"])

# Stripe-Signature header schema: ``t=<unix_ts>,v1=<hex_signature>`` (with
# optional additional ``vN=<hex>`` segments). Reject anything that does
# not match this shape — we do NOT perform HMAC verification in v1.2
# (that arrives in v1.3 via stripe.Webhook.construct_event).
_STRIPE_SIG_PATTERN = re.compile(r"^t=\d+,(v\d+=[a-fA-F0-9]+,?)+$")


@billing_router.post(
    "/checkout",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=StubResponse,
)
async def checkout_stub(
    body: CheckoutRequest,
    user: User = Depends(get_authenticated_user),
) -> StubResponse:
    """Return 501 stub — actual Stripe Checkout in v1.3."""
    logger.info(
        "Billing checkout stub invoked user_id=%s plan=%s",
        user.id, body.plan,
    )
    return StubResponse()


@billing_router.post(
    "/webhook",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=StubResponse,
)
async def webhook_stub(
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
) -> StubResponse:
    """Validate Stripe-Signature header schema (rejects malformed); return 501.

    Webhook stub does NOT require auth (Stripe calls it server-to-server).
    Real HMAC signature verification arrives in v1.3.
    """
    if not stripe_signature or not _STRIPE_SIG_PATTERN.match(stripe_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe-Signature header schema",
        )
    return StubResponse()
