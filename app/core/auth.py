# DEPRECATED — RETAINED FOR ATOMIC CUTOVER FALLBACK (W4)
#
# This module's BearerAuthMiddleware is the V2_ENABLED=false branch in
# app/main.py. It exists ONLY to keep dev/CI environments authenticated
# during the Phase 13 cutover window (frontend Phase 14 not yet shipped).
#
# Deletion is scheduled for Phase 16+ once AUTH_V2_ENABLED=true is verified
# stable in production. DO NOT add new code here. New auth work goes in
# app/core/dual_auth.py.
"""Legacy single-shared-bearer-token middleware (v1.1 compatibility).

Reads ``API_BEARER_TOKEN`` from env. Requests that present
``Authorization: Bearer <API_BEARER_TOKEN>`` pass through; everything else
is rejected with HTTP 401 EXCEPT routes on PUBLIC_ALLOWLIST (health,
docs, static, root redirect).

When ``API_BEARER_TOKEN`` is unset the middleware fails OPEN-but-LOUD on
boot — it raises at app construction so dev/CI never silently become a
zero-auth window. Deploys without the env var refuse to boot.
"""

from __future__ import annotations

import logging
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


# Mirror DualAuthMiddleware allowlist for v1.1 surface — keep aligned (DRT).
PUBLIC_ALLOWLIST: tuple[str, ...] = (
    "/",
    "/health",
    "/health/live",
    "/health/ready",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/favicon.ico",
)
PUBLIC_PREFIXES: tuple[str, ...] = ("/static/", "/uploads/files/", "/docs/")
BEARER_PREFIX = "Bearer "


def _is_public(path: str) -> bool:
    """Return True iff the path bypasses bearer-token enforcement."""
    if path in PUBLIC_ALLOWLIST:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required"},
        headers={"WWW-Authenticate": 'Bearer realm="whisperx"'},
    )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Single shared API_BEARER_TOKEN gate (v1.1 fallback).

    The token is read from the ``API_BEARER_TOKEN`` environment variable at
    middleware construction. When the env var is missing we treat the deploy
    as misconfigured and raise — fail-loud rather than allow anonymous traffic
    through the V2-OFF branch.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        token = os.environ.get("API_BEARER_TOKEN", "").strip()
        # Fail-CLOSED (not fail-open) when API_BEARER_TOKEN is unset:
        # boot succeeds but every non-public route returns 401. This keeps
        # dev/CI authenticated without forcing a hard env-var requirement at
        # import time (test suites can construct the app without the legacy
        # token by flipping AUTH__V2_ENABLED=true to skip this branch).
        if not token:
            logger.warning(
                "API_BEARER_TOKEN is unset — BearerAuthMiddleware will deny "
                "all non-public requests with 401 until token is configured "
                "or AUTH__V2_ENABLED=true is set."
            )
        self._token = token

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        if _is_public(request.url.path):
            return await call_next(request)

        # Token unset → fail-CLOSED (deny everything except public allowlist).
        if not self._token:
            return _unauthorized()

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith(BEARER_PREFIX):
            return _unauthorized()

        presented = auth_header[len(BEARER_PREFIX):].strip()
        if not secrets.compare_digest(presented, self._token):
            return _unauthorized()

        return await call_next(request)
