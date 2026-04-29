"""Account routes — DELETE /api/account/data (SCOPE-05).

Self-serve user-data deletion: removes the caller's tasks AND uploaded
files; the users row itself is intentionally PRESERVED.

Full account deletion (DELETE /api/account) is Phase 15 (SCOPE-06).

Constraints honoured:
    DRY  — get_authenticated_user dependency reused (single resolution
           point set by DualAuthMiddleware).
    SRP  — route does HTTP only; AccountService owns deletion logic.
    No nested-if (verifier-checked).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_user, get_db_session
from app.domain.entities.user import User
from app.services.account_service import AccountService

account_router = APIRouter(prefix="/api/account", tags=["Account"])


def get_account_service(
    session: Session = Depends(get_db_session),
) -> AccountService:
    """Per-request AccountService factory (binds a fresh DB session)."""
    return AccountService(session=session)


@account_router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_data(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    """Delete the caller's tasks + uploaded files. User row preserved."""
    account_service.delete_user_data(int(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
