"""Account routes — DELETE /api/account/data (SCOPE-05) + GET /api/account/me (UI-07) + DELETE /api/account (SCOPE-06).

SCOPE-05: self-serve user-data deletion — caller's tasks + uploaded files;
the users row itself is intentionally PRESERVED.
UI-07:    server-side hydration source-of-truth — returns the safe-to-render
fields (user_id/email/plan_tier/trial_started_at/token_version) for the
frontend authStore.refresh() and AccountPage.
SCOPE-06: full-row account delete + 3-step cascade orchestrated by
AccountService.delete_account; clears auth cookies on success.

Phase 19 — pilot route migration to the Depends auth chain:
- Auth resolved via the authenticated_user Depends (NOT the deleted legacy
  middleware request.state lookup).
- CSRF enforced router-level via the csrf_protected Depends; csrf_protected
  method-gates so GET /me passes through, DELETEs fire the double-submit
  check.
- AccountService bound via get_account_service_v2 (chains off get_db ->
  get_user_repository_v2). Local helper preserved for backward compat
  callers; switched to the get_db Depends (was get_db_session).

Constraints honoured:
    DRY  — authenticated_user dependency reused (single resolution
           point per Phase 19 D2 lock); AccountSummaryResponse +
           DeleteAccountRequest imported from the central account_schemas
           module; clear_auth_cookies imported from _cookie_helpers.
    SRP  — routes do HTTP only; AccountService owns business logic.
    No nested-if (verifier-checked).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api._cookie_helpers import clear_auth_cookies
from app.api.dependencies import (
    authenticated_user,
    csrf_protected,
    get_account_service_v2,
    get_db,
)
from app.api.schemas.account_schemas import (
    AccountSummaryResponse,
    DeleteAccountRequest,
)
from app.core.exceptions import ValidationError
from app.domain.entities.user import User
from app.services.account_service import AccountService

account_router = APIRouter(
    prefix="/api/account",
    tags=["Account"],
    dependencies=[Depends(csrf_protected)],
)


def get_account_service(
    session: Session = Depends(get_db),
) -> AccountService:
    """Per-request AccountService factory (binds a fresh DB session).

    Kept for backward compat with any external callers; new routes
    composes ``get_account_service_v2`` directly. AccountService
    lazy-constructs the user repository when only ``session`` is passed.
    """
    return AccountService(session=session)


@account_router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_data(
    user: User = Depends(authenticated_user),
    account_service: AccountService = Depends(get_account_service_v2),
) -> Response:
    """Delete the caller's tasks + uploaded files. User row preserved."""
    account_service.delete_user_data(int(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@account_router.get("/me", response_model=AccountSummaryResponse)
async def get_account_me(
    user: User = Depends(authenticated_user),
    account_service: AccountService = Depends(get_account_service_v2),
) -> AccountSummaryResponse:
    """GET /api/account/me — return account summary for client hydration (UI-07).

    Anti-enumeration design (WR-03 — deliberate, NOT a missing 404):
    AccountService.get_account_summary raises InvalidCredentialsError
    when the users row is gone (race-condition self-delete or admin
    purge). The global exception handler maps this to HTTP 401, which
    is intentionally indistinguishable from session-expired from the
    client's perspective.

    Frontend contract: ``fetchAccountSummary`` sets ``suppress401Redirect``,
    so apiClient throws AuthRequiredError; ``authStore.refresh()`` catches
    it and silently clears the user. Effect: a stale-session client sees
    a sign-out instead of a "your row vanished" error — uniform with
    every other 401 surface (T-15-05). Future maintainers: do NOT
    "improve" this to 404, you would re-introduce the enumeration leak.
    """
    summary = account_service.get_account_summary(int(user.id))
    return AccountSummaryResponse(**summary)


@account_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    user: User = Depends(authenticated_user),
    account_service: AccountService = Depends(get_account_service_v2),
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
