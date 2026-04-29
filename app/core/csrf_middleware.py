"""CsrfMiddleware — double-submit CSRF on cookie-auth state-mutating routes.

Per .planning/phases/13-atomic-backend-cutover/13-CONTEXT.md §55 + MID-04 (locked):

Behaviour:
  - GET / HEAD / OPTIONS                       → bypass (no state-mutation).
  - ``request.state.auth_method == 'bearer'``  → bypass (external API clients).
  - ``request.state.auth_method is None``      → bypass (public allowlist).
  - ``request.state.auth_method == 'cookie'``
    on POST / PUT / PATCH / DELETE             → enforce double-submit:
      ``X-CSRF-Token`` header == ``csrf_token`` cookie via
      ``secrets.compare_digest`` (CsrfService.verify).

Wired AFTER DualAuthMiddleware in app/main.py (Plan 13-09) so that
``request.state.auth_method`` is populated before this runs.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.container import Container

logger = logging.getLogger(__name__)


STATE_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"


def _csrf_error(detail: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": detail})


class CsrfMiddleware(BaseHTTPMiddleware):
    """Enforce double-submit CSRF on cookie-authenticated state-mutating routes.

    Single-responsibility: CSRF only. No business logic, no state writes,
    no auth resolution (DualAuthMiddleware owns that).
    """

    def __init__(self, app: ASGIApp, *, container: Container) -> None:
        super().__init__(app)
        self._container = container

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in STATE_MUTATING_METHODS:
            return await call_next(request)

        auth_method = getattr(request.state, "auth_method", None)
        if auth_method != "cookie":
            # bearer or public allowlist — skip CSRF.
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        header_token = request.headers.get(CSRF_HEADER, "")
        if not header_token:
            return _csrf_error("CSRF token missing")
        if not self._container.csrf_service().verify(cookie_token, header_token):
            return _csrf_error("CSRF token mismatch")
        return await call_next(request)
