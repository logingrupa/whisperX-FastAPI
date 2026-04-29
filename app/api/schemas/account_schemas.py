"""Pydantic v2 schemas for ``/api/account/*`` routes (Phase 15).

Single source of truth for the account-summary response and the
delete-account request bodies. Routes import these names directly —
never duplicate field definitions inline.

Constraints honoured:
    DRY  — schemas defined once; AccountService.get_account_summary +
           account_routes.delete_account both import from here.
    SRP  — pure DTOs; no business logic, no validation against external
           state (mismatch check happens at service boundary).
    No nested-if (verifier-checked: ``grep -cE "^\\s+if .*\\bif\\b"`` == 0).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AccountSummaryResponse(BaseModel):
    """GET /api/account/me — server-side hydration source of truth.

    Field allowlist enforces T-15-11: only safe-to-render fields cross
    the wire (no password_hash, no token, no csrf).
    """

    user_id: int
    email: EmailStr
    plan_tier: str = Field(..., description="One of free|trial|pro|team")
    trial_started_at: datetime | None = None
    token_version: int = Field(
        ..., description="For cross-tab refresh debounce"
    )


class DeleteAccountRequest(BaseModel):
    """DELETE /api/account body.

    ``email_confirm`` validated against ``request.state.user.email``
    (case-insensitive) at the service boundary; parse-time enforces
    well-formed email shape only.
    """

    email_confirm: EmailStr = Field(
        ...,
        description="Must equal request.state.user.email (case-insensitive)",
    )
