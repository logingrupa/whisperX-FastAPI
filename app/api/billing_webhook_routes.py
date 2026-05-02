"""Billing webhook router — Stripe webhook stub (BILL-06).

SPLIT from ``app.api.billing_routes`` in Phase 19-07. The webhook is
auth-free (Stripe calls server-to-server) and CSRF-free (no browser
double-submit possible from a server-to-server caller). Splitting it
into a separate router lets ``billing_router`` apply router-level
``Depends(csrf_protected)`` cleanly while ``billing_webhook_router``
stays naked — FastAPI does NOT support per-route dependency removal,
hence the file split.

BILL-07: ``stripe`` is imported at module-load only — ZERO runtime
``stripe.*`` calls in v1.2. Real ``stripe.Webhook.construct_event``
arrives in v1.3 alongside full HMAC signature verification.

Constraints honoured:
    DRY  — single ``_STRIPE_SIG_PATTERN`` regex source for the schema
           check; reused if a v1.3 fallback path also wants the schema
           pre-check.
    SRP  — webhook router owns ONLY the /webhook endpoint; checkout
           lives on ``billing_router`` (which carries auth + CSRF).
    No nested-if (verifier-checked).
"""

from __future__ import annotations

import logging
import re

import stripe  # noqa: F401  # BILL-07 — module-load import only; no runtime calls

from fastapi import APIRouter, Header, HTTPException, status

from app.api.schemas.billing_schemas import StubResponse

logger = logging.getLogger(__name__)

billing_webhook_router = APIRouter(prefix="/billing", tags=["Billing"])

# Stripe-Signature header schema: ``t=<unix_ts>,v1=<hex_signature>`` (with
# optional additional ``vN=<hex>`` segments). Reject anything that does
# not match this shape — we do NOT perform HMAC verification in v1.2
# (that arrives in v1.3 via stripe.Webhook.construct_event).
_STRIPE_SIG_PATTERN = re.compile(r"^t=\d+,(v\d+=[a-fA-F0-9]+,?)+$")


@billing_webhook_router.post(
    "/webhook",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=StubResponse,
)
async def webhook_stub(
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
) -> StubResponse:
    """Validate Stripe-Signature header schema (rejects malformed); return 501.

    Webhook stub does NOT require auth (Stripe calls it server-to-server)
    and is exempt from CSRF (server-to-server has no browser cookie). Real
    HMAC signature verification arrives in v1.3.
    """
    if not stripe_signature or not _STRIPE_SIG_PATTERN.match(stripe_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe-Signature header schema",
        )
    return StubResponse()
