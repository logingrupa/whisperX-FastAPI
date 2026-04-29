"""Account routes — DELETE /api/account/data (SCOPE-05) + GET /api/account/me (UI-07) + DELETE /api/account (SCOPE-06).

SCOPE-05: self-serve user-data deletion — caller's tasks + uploaded files;
the users row itself is intentionally PRESERVED.
UI-07:    server-side hydration source-of-truth — returns the safe-to-render
fields (user_id/email/plan_tier/trial_started_at/token_version) for the
frontend authStore.refresh() and AccountPage.
SCOPE-06: full-row account delete + 3-step cascade orchestrated by
AccountService.delete_account; clears auth cookies on success.

Constraints honoured:
    DRY  — get_authenticated_user dependency reused (single resolution
           point set by DualAuthMiddleware); AccountSummaryResponse +
           DeleteAccountRequest imported from the central account_schemas
           module; clear_auth_cookies imported from _cookie_helpers.
    SRP  — routes do HTTP only; AccountService owns business logic.
    No nested-if (verifier-checked).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api._cookie_helpers import clear_auth_cookies
from app.api.dependencies import get_authenticated_user, get_db_session
from app.api.schemas.account_schemas import (
    AccountSummaryResponse,
    DeleteAccountRequest,
)
from app.core.exceptions import ValidationError
from app.domain.entities.user import User
from app.services.account_service import AccountService

account_router = APIRouter(prefix="/api/account", tags=["Account"])


def get_account_service(
    session: Session = Depends(get_db_session),
) -> AccountService:
    """Per-request AccountService factory (binds a fresh DB session).

    AccountService lazy-constructs the user repository when only ``session``
    is passed — keeps SCOPE-05 callers untouched while UI-07 / SCOPE-06
    benefit from the shared instance.
    """
    return AccountService(session=session)


@account_router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_data(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    """Delete the caller's tasks + uploaded files. User row preserved."""
    account_service.delete_user_data(int(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@account_router.get("/me", response_model=AccountSummaryResponse)
async def get_account_me(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> AccountSummaryResponse:
    """GET /api/account/me — return account summary for client hydration (UI-07)."""
    summary = account_service.get_account_summary(int(user.id))
    return AccountSummaryResponse(**summary)


@account_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    """DELETE /api/account — cascade delete + clear cookies. SCOPE-06.

    Body: ``{email_confirm: EmailStr}`` — case-insensitive match against
    ``request.state.user.email`` enforced by AccountService.delete_account.

    Mismatched email → 400 EMAIL_CONFIRM_MISMATCH (locked contract per
    CONTEXT D-RES). Service-layer ValidationError is re-raised as 400 here
    rather than letting it surface as the global handler default of 422 —
    route-local translation keeps other ValidationError sites unaffected.

    Cookie-clearing pattern (T-15-04): build a NEW Response(204) and call
    ``clear_auth_cookies`` on it; never reuse a Depends-injected Response,
    or FastAPI drops the Set-Cookie deletions.
    """
    try:
        account_service.delete_account(int(user.id), body.email_confirm)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "message": exc.user_message,
                    "code": exc.code,
                }
            },
        )

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response
