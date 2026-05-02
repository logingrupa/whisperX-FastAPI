"""DualAuthMiddleware — cookie session JWT OR ``whsk_*`` bearer (Phase 13).

Per .planning/phases/13-atomic-backend-cutover/13-CONTEXT.md §46-56 (locked):

Resolution order on every HTTP request:
  1. ``Authorization: Bearer whsk_*`` → ``auth_method='bearer'``;
     resolve via ``KeyService.verify_plaintext``; sets ``request.state.user``,
     ``request.state.api_key_id``, ``request.state.plan_tier``.
  2. ``Cookie session=<jwt>`` → ``auth_method='cookie'``;
     verify via ``TokenService.verify_and_refresh``; sets ``request.state.user``,
     ``request.state.plan_tier``; re-issues sliding-refresh cookie (AUTH-04).
  3. Path in ``PUBLIC_ALLOWLIST`` → pass-through; ``request.state.user = None``.
  4. Else → 401 JSON ``{"detail": "Authentication required"}``.

Bearer wins when both presented (CONTEXT §50).

WebSocket scopes (``scope["type"] == "websocket"``) are not handled here:
Starlette's ``BaseHTTPMiddleware`` only dispatches HTTP. WS endpoints get auth
via the dedicated ticket flow (Plan 13-08).

Logging discipline (T-13-04): only ``auth_method`` + ``user_id`` are logged;
raw JWTs and plaintext API keys are never emitted.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core import jwt_codec
from app.core.config import get_settings
from app.core.container import Container
from app.core.exceptions import (
    InvalidApiKeyFormatError,
    InvalidApiKeyHashError,
    JwtAlgorithmError,
    JwtExpiredError,
    JwtTamperedError,
)

logger = logging.getLogger(__name__)


PUBLIC_ALLOWLIST: tuple[str, ...] = (
    "/health",
    "/health/live",
    "/health/ready",
    "/",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/static",
    "/favicon.ico",
    "/auth/register",
    "/auth/login",
    "/ui/login",
    "/ui/register",
    # Stripe calls /billing/webhook server-to-server; authenticity is via
    # Stripe-Signature HMAC (validated in v1.3 — Phase 13-05 stub only
    # checks header schema). Auth is intentionally omitted.
    "/billing/webhook",
)
PUBLIC_PREFIXES: tuple[str, ...] = ("/static/", "/uploads/files/")
SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"
BEARER_PREFIX = "Bearer "


def _is_public(path: str) -> bool:
    """Return True iff the path is on the locked public-allowlist (MID-03)."""
    if path in PUBLIC_ALLOWLIST:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _unauthorized() -> JSONResponse:
    """Single 401 shape — no leak about which auth leg failed (T-13-05)."""
    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required"},
        headers={"WWW-Authenticate": 'Bearer realm="whisperx"'},
    )


def _set_state_anonymous(request: Request) -> None:
    """Public-allowlist contract — request.state populated with None values."""
    request.state.user = None
    request.state.plan_tier = None
    request.state.auth_method = None
    request.state.api_key_id = None


def _logout_clear_cookies(response: Response) -> None:
    """Clear session + csrf_token cookies (used by /auth/logout in plan 13-03).

    Exported helper so /auth/logout never duplicates cookie-attribute knowledge
    (DRY): it always matches the attrs the middleware sets when issuing.
    """
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    response.delete_cookie(key=CSRF_COOKIE, path="/")


_BEARER_FAILURE_EXCEPTIONS = (
    InvalidApiKeyFormatError,
    InvalidApiKeyHashError,
)
_COOKIE_DECODE_EXCEPTIONS = (
    JwtExpiredError,
    JwtAlgorithmError,
    JwtTamperedError,
    KeyError,
    ValueError,
)
_COOKIE_REFRESH_EXCEPTIONS = (
    JwtExpiredError,
    JwtAlgorithmError,
    JwtTamperedError,
)


class DualAuthMiddleware(BaseHTTPMiddleware):
    """Resolve cookie session JWT OR ``whsk_*`` bearer; populate request.state.

    Single source of auth context for all Phase 13 routes (DRT). Routes never
    parse Authorization or session cookies directly — they consume
    ``Depends(get_authenticated_user)`` which reads ``request.state.user``.

    Failure model: on a credential-bearing request that fails to validate
    (bad bearer, bad cookie), the middleware falls through to the public
    allowlist when the path is public. Without this, a stale browser cookie
    locks the user out of the recovery routes (/auth/login, /auth/register).
    Non-public paths still 401 fast — security posture unchanged.
    """

    def __init__(self, app: ASGIApp, *, container: Container) -> None:
        super().__init__(app)
        self._container = container

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        is_public_path = _is_public(request.url.path)
        bearer = self._extract_bearer(request)
        if bearer is not None:
            return await self._dispatch_bearer(
                request, call_next, bearer, is_public_path
            )

        cookie = request.cookies.get(SESSION_COOKIE)
        if cookie:
            return await self._dispatch_cookie(
                request, call_next, cookie, is_public_path
            )

        if is_public_path:
            return await self._call_anonymous(request, call_next)

        return _unauthorized()

    # -- bearer ---------------------------------------------------------

    @staticmethod
    def _extract_bearer(request: Request) -> str | None:
        header = request.headers.get("authorization", "")
        if not header.startswith(BEARER_PREFIX):
            return None
        return header[len(BEARER_PREFIX) :].strip() or None

    async def _dispatch_bearer(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        plaintext: str,
        is_public_path: bool,
    ) -> Response:
        result = self._resolve_bearer(plaintext)
        if result is None:
            return await self._reject_or_anonymous(request, call_next, is_public_path)
        user, api_key_id = result
        self._set_state(request, user=user, method="bearer", api_key_id=api_key_id)
        logger.debug("auth ok auth_method=bearer user_id=%s", user.id)
        return await call_next(request)

    def _resolve_bearer(self, plaintext: str):
        """Resolve bearer plaintext to (User, api_key_id) or None.

        Owns the lifecycle of every Factory-provided service it constructs:
        each service has an underlying SQLAlchemy ``Session`` checked out
        from the engine pool, and that Session MUST be closed in a finally
        clause. Otherwise the pool exhausts after pool_size + max_overflow
        (default 5+10=15) requests and the next checkout blocks 30s on
        QueuePool timeout — surfacing as a 401 because
        ``SQLAlchemyUserRepository.get_by_email`` swallows the
        ``SQLAlchemyError`` and returns None. Same root cause and same
        contract as the FastAPI ``Depends`` providers in
        ``app/api/dependencies.py``; this middleware bypasses Depends so
        it must do the cleanup itself.
        """
        key_service = self._container.key_service()
        try:
            try:
                api_key = key_service.verify_plaintext(plaintext)
            except _BEARER_FAILURE_EXCEPTIONS:
                return None
        finally:
            key_service.repository.session.close()

        user_repository = self._container.user_repository()
        try:
            user = user_repository.get_by_id(api_key.user_id)
        finally:
            user_repository.session.close()
        if user is None:
            return None
        return user, api_key.id

    # -- cookie ---------------------------------------------------------

    async def _dispatch_cookie(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        token: str,
        is_public_path: bool,
    ) -> Response:
        result = self._resolve_cookie(token)
        if result is None:
            return await self._reject_or_anonymous(request, call_next, is_public_path)
        user, refreshed_token = result
        self._set_state(request, user=user, method="cookie")
        response = await call_next(request)
        self._set_session_cookie(response, refreshed_token)
        logger.debug("auth ok auth_method=cookie user_id=%s", user.id)
        return response

    def _resolve_cookie(self, token: str):
        """Resolve session cookie token to (User, refreshed_token) or None.

        Same Session lifecycle contract as ``_resolve_bearer``:
        the Factory-provided ``user_repository`` owns a fresh DB Session
        and must be closed in a finally clause to keep the pool alive.
        ``token_service`` is a Singleton (no DB) so it does not require
        a close.
        """
        secret = get_settings().auth.JWT_SECRET.get_secret_value()
        try:
            payload = jwt_codec.decode_session(token, secret=secret)
            user_id = int(payload["sub"])
        except _COOKIE_DECODE_EXCEPTIONS:
            return None

        user_repository = self._container.user_repository()
        try:
            user = user_repository.get_by_id(user_id)
        finally:
            user_repository.session.close()
        if user is None:
            return None

        try:
            _payload, refreshed_token = self._container.token_service().verify_and_refresh(
                token, user.token_version
            )
        except _COOKIE_REFRESH_EXCEPTIONS:
            return None
        return user, refreshed_token

    # -- shared helpers -------------------------------------------------

    @staticmethod
    def _set_state(
        request: Request,
        *,
        user,
        method: str,
        api_key_id: int | None = None,
    ) -> None:
        request.state.user = user
        request.state.plan_tier = user.plan_tier
        request.state.auth_method = method
        request.state.api_key_id = api_key_id

    @staticmethod
    async def _call_anonymous(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        _set_state_anonymous(request)
        return await call_next(request)

    async def _reject_or_anonymous(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        is_public_path: bool,
    ) -> Response:
        if not is_public_path:
            return _unauthorized()
        return await self._call_anonymous(request, call_next)

    def _set_session_cookie(self, response: Response, token: str) -> None:
        settings = get_settings()
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=settings.auth.JWT_TTL_DAYS * 24 * 3600,
            httponly=True,
            secure=settings.auth.COOKIE_SECURE,
            samesite="lax",
            path="/",
            domain=settings.auth.COOKIE_DOMAIN or None,
        )
