"""Account routes — DELETE /api/account/data (SCOPE-05) + GET /api/account/me (UI-07).

SCOPE-05: self-serve user-data deletion — caller's tasks + uploaded files;
the users row itself is intentionally PRESERVED.
UI-07:    server-side hydration source-of-truth — returns the safe-to-render
fields (user_id/email/plan_tier/trial_started_at/token_version) for the
frontend authStore.refresh() and AccountPage.

Full account deletion (DELETE /api/account) is Plan 15-04 (SCOPE-06).

Constraints honoured:
    DRY  — get_authenticated_user dependency reused (single resolution
           point set by DualAuthMiddleware); AccountSummaryResponse imported
           from the central account_schemas module.
    SRP  — routes do HTTP only; AccountService owns business logic.
    No nested-if (verifier-checked).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_user, get_db_session
from app.api.schemas.account_schemas import AccountSummaryResponse
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
