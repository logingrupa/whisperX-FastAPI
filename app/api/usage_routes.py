"""Usage routes — GET /api/usage (read-only token-bucket + trial summary).

Quick task 260505-l2w: surfaces the rate-limit + trial state the backend
already records, sourced from ``rate_limit_buckets`` (refill-on-read) +
``users.trial_started_at`` + ``users.plan_tier``. Single read-only endpoint
that ``/dashboard/usage`` consumes; no mutation, no aggregation outside the
service layer.

Phase 19 — Depends auth chain (single namespace):
- Auth resolved via the ``authenticated_user`` Depends.
- CSRF enforced router-level via the ``csrf_protected`` Depends; csrf_protected
  method-gates so GET /api/usage passes through without an X-CSRF-Token.
- UsageQueryService bound via ``get_usage_query_service`` (chains off
  ``get_db`` -> ``get_user_repository`` + ``get_rate_limit_repository``).

Constraints honoured:
    DRY  — single endpoint per concept; ``UsageSummaryResponse`` is the
           sole wire-shape definition.
    SRP  — route does HTTP only; UsageQueryService owns business logic;
           rate-limit repo owns SQL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    authenticated_user,
    csrf_protected,
    get_usage_by_key_service,
    get_usage_query_service,
)
from app.api.schemas.usage_schemas import (
    UsageByKeyResponse,
    UsageSummaryResponse,
)
from app.domain.entities.user import User
from app.services.usage_by_key_service import UsageByKeyService
from app.services.usage_query_service import UsageQueryService

usage_router = APIRouter(
    prefix="/api/usage",
    tags=["Usage"],
    dependencies=[Depends(csrf_protected)],
)


@usage_router.get("", response_model=UsageSummaryResponse)
async def get_usage(
    user: User = Depends(authenticated_user),
    usage_query_service: UsageQueryService = Depends(get_usage_query_service),
) -> UsageSummaryResponse:
    """Return the caller's current usage summary."""
    summary = usage_query_service.get_summary(int(user.id))
    return UsageSummaryResponse(**summary)


@usage_router.get("/by-key", response_model=UsageByKeyResponse)
async def get_usage_by_key(
    user: User = Depends(authenticated_user),
    usage_by_key_service: UsageByKeyService = Depends(get_usage_by_key_service),
) -> UsageByKeyResponse:
    """Return the caller's historical usage grouped by API key.

    NULL-key rows (pre-attribution history, cookie/session transcriptions,
    deleted keys) collapse into a single 'unattributed' entry.
    """
    keys = usage_by_key_service.get_breakdown(int(user.id))
    return UsageByKeyResponse(keys=keys)
