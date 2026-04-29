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


class DualAuthMiddleware(BaseHTTPMiddleware):
    """Resolve cookie session JWT OR ``whsk_*`` bearer; populate request.state.

    Single source of auth context for all Phase 13 routes (DRT). Routes never
    parse Authorization or session cookies directly — they consume
    ``Depends(get_authenticated_user)`` which reads ``request.state.user``.
    """

    def __init__(self, app: ASGIApp, *, container: Container) -> None:
        super().__init__(app)
        self._container = container

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        # 1. Bearer first — external API consumers; bearer wins over cookie.
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith(BEARER_PREFIX):
            plaintext = auth_header[len(BEARER_PREFIX) :].strip()
            return await self._dispatch_bearer(request, call_next, plaintext)

        # 2. Cookie session — browser flow with sliding refresh.
        session_cookie = request.cookies.get(SESSION_COOKIE)
        if session_cookie:
            return await self._dispatch_cookie(request, call_next, session_cookie)

        # 3. Public allowlist — pass-through with anonymous state.
        if _is_public(request.url.path):
            _set_state_anonymous(request)
            return await call_next(request)

        # 4. Else: 401.
        return _unauthorized()

    async def _dispatch_bearer(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        plaintext: str,
    ) -> Response:
        try:
            api_key = self._container.key_service().verify_plaintext(plaintext)
        except (InvalidApiKeyFormatError, InvalidApiKeyHashError):
            return _unauthorized()

        user = self._container.user_repository().get_by_id(api_key.user_id)
        if user is None:
            return _unauthorized()

        request.state.user = user
        request.state.plan_tier = user.plan_tier
        request.state.auth_method = "bearer"
        request.state.api_key_id = api_key.id
        logger.debug("auth ok auth_method=bearer user_id=%s", user.id)
        return await call_next(request)

    async def _dispatch_cookie(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        token: str,
    ) -> Response:
        # Decode once to recover sub before token-version compare; typed errors
        # collapse to a generic 401 (T-13-02 / T-13-05).
        try:
            payload = jwt_codec.decode_session(
                token, secret=get_settings().auth.JWT_SECRET.get_secret_value()
            )
            user_id = int(payload["sub"])
        except (JwtExpiredError, JwtAlgorithmError, JwtTamperedError, KeyError, ValueError):
            return _unauthorized()

        user = self._container.user_repository().get_by_id(user_id)
        if user is None:
            return _unauthorized()

        # Verify token_version + issue refreshed token (AUTH-04 sliding window).
        try:
            _payload, new_token = self._container.token_service().verify_and_refresh(
                token, user.token_version
            )
        except (JwtExpiredError, JwtAlgorithmError, JwtTamperedError):
            return _unauthorized()

        request.state.user = user
        request.state.plan_tier = user.plan_tier
        request.state.auth_method = "cookie"
        request.state.api_key_id = None

        response = await call_next(request)
        self._set_session_cookie(response, new_token)
        logger.debug("auth ok auth_method=cookie user_id=%s", user.id)
        return response

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
