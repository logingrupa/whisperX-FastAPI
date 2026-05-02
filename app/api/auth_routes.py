"""Auth routes — register, login, logout (Phase 13).

Exposes ``mailto:hey@logingrupa.lv`` as the password-reset path per AUTH-07
(no SMTP in v1.2; operator-handled).

Locked policy (CONTEXT §74 + Phase 13-03 PLAN):

* ``POST /auth/register`` — rate-limited 3/hr per IP /24 (ANTI-01); generic
  422 ``"Registration failed"`` on either duplicate-email OR
  disposable-domain rejection (anti-enumeration: identical body+code on
  both legs — T-13-09).
* ``POST /auth/login`` — rate-limited 10/hr per IP /24 (ANTI-02); generic
  401 via ``InvalidCredentialsError`` for either wrong-email OR
  wrong-password (T-13-10).
* ``POST /auth/logout`` — clears ``session`` + ``csrf_token`` cookies; 204;
  idempotent (no-op if no session).

Logging discipline (T-13-13): only event labels — never email or password.

Constraints honoured:
    DRY  — ``_set_auth_cookies`` / ``_clear_auth_cookies`` extracted; cookie
           attrs read from ``settings.auth.*`` (single source).
    SRP  — routes do HTTP only; AuthService.register / .login own business
           logic; CsrfService issues CSRF tokens.
    No nested-if (verifier-checked: ``grep -cE "^\\s+if .*\\bif\\b"`` == 0).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status

from app.api._cookie_helpers import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    clear_auth_cookies,
)
from app.api.dependencies import (
    authenticated_user,
    csrf_protected,
    get_auth_service,
)
from app.core.services import get_csrf_service
from app.api.schemas.auth_schemas import AuthResponse, LoginRequest, RegisterRequest
from app.core.config import get_settings
from app.core.disposable_email import is_disposable
from app.core.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    ValidationError,
)
from app.core.rate_limiter import limiter
from app.domain.entities.user import User
from app.services.auth import AuthService, CsrfService

logger = logging.getLogger(__name__)

PASSWORD_RESET_HINT = (
    "Password reset is manual — please email hey@logingrupa.lv (AUTH-07)."
)

# Anti-enumeration: identical message + code for disposable + duplicate
# rejection. Constants force DRY use; verifier greps both ≥2.
_REGISTRATION_FAILED_MESSAGE = "Registration failed"
_REGISTRATION_FAILED_CODE = "REGISTRATION_FAILED"


auth_router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={
        429: {"description": "Too many requests — see Retry-After header"},
    },
)


def _set_auth_cookies(
    response: Response, *, session_token: str, csrf_token: str
) -> None:
    """Stamp session + csrf cookies on the response (cookie attrs locked
    in CONTEXT §60-67).
    """
    settings = get_settings()
    max_age = settings.auth.JWT_TTL_DAYS * 24 * 3600
    domain = settings.auth.COOKIE_DOMAIN or None
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth.COOKIE_SECURE,
        samesite="lax",
        path="/",
        domain=domain,
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.auth.COOKIE_SECURE,
        samesite="lax",
        path="/",
        domain=domain,
    )


def _registration_failed() -> ValidationError:
    """Build the canonical anti-enumeration ValidationError."""
    return ValidationError(
        message=_REGISTRATION_FAILED_MESSAGE,
        code=_REGISTRATION_FAILED_CODE,
        user_message=_REGISTRATION_FAILED_MESSAGE,
    )


@auth_router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=AuthResponse,
    description=f"Register a new user. {PASSWORD_RESET_HINT}",
)
@limiter.limit("3/hour")
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    csrf_service: CsrfService = Depends(get_csrf_service),
) -> AuthResponse:
    """Register a new user account.

    Returns 201 with ``Set-Cookie: session=...`` + ``csrf_token=...``.
    Rate-limited 3/hr per /24 subnet (ANTI-01).
    """
    # ANTI-04: disposable email blocklist check (generic error)
    if is_disposable(body.email):
        logger.info("Registration rejected disposable_domain")
        raise _registration_failed()
    try:
        user = auth_service.register(body.email, body.password)
    except UserAlreadyExistsError as exc:
        # Anti-enumeration: identical body + code as disposable rejection
        # (T-13-09 mitigation).
        logger.info("Registration rejected duplicate id_unknown")
        raise _registration_failed() from exc
    # Auto-login on register: issue session + CSRF cookies
    session_token = auth_service.token_service.issue(int(user.id), user.token_version)
    csrf_token = csrf_service.issue()
    _set_auth_cookies(response, session_token=session_token, csrf_token=csrf_token)
    return AuthResponse(user_id=int(user.id), plan_tier=user.plan_tier)


@auth_router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=AuthResponse,
    description=f"Log in. {PASSWORD_RESET_HINT}",
)
@limiter.limit("10/hour")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
    csrf_service: CsrfService = Depends(get_csrf_service),
) -> AuthResponse:
    """Authenticate and issue session + CSRF cookies.

    Generic 401 ``"Invalid credentials"`` on either wrong-email or
    wrong-password (T-13-10). Rate-limited 10/hr per /24 (ANTI-02).
    """
    try:
        user, session_token = auth_service.login(body.email, body.password)
    except InvalidCredentialsError:
        logger.info("Login rejected invalid_credentials")
        raise
    csrf_token = csrf_service.issue()
    _set_auth_cookies(response, session_token=session_token, csrf_token=csrf_token)
    return AuthResponse(user_id=int(user.id), plan_tier=user.plan_tier)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    """Clear session + CSRF cookies. Idempotent — no-op if no session.

    Returns a brand-new Response (not the injected one) so the Set-Cookie
    deletions are emitted on the wire. Using the injected ``Response``
    parameter combined with ``return Response(...)`` discards the deletion
    headers (FastAPI ignores the injected response when an explicit one is
    returned).
    """
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@auth_router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(csrf_protected)],
)
async def logout_all(
    user: User = Depends(authenticated_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """POST /auth/logout-all — bump token_version + clear cookies. AUTH-06.

    Invalidates every JWT issued for this user (including the caller's own
    cookie) by bumping ``users.token_version``. The next middleware ver-check
    401s any outstanding session (T-15-03). Cookie clearing is for client UX
    — the JWTs are already dead server-side. Mirrors /auth/logout's
    fresh-Response pattern (T-15-04 — see logout above for rationale).
    """
    auth_service.logout_all_devices(int(user.id))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response
