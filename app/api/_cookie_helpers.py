"""Shared cookie helpers for auth-mutating routes (Phase 15-01).

Single source of truth for session and CSRF cookie names plus the
``clear_auth_cookies`` function. Imported by ``auth_routes`` (logout,
logout-all in Phase 15-03) and ``account_routes`` (DELETE /api/account in
Phase 15-04). DRY per Phase 15 CONTEXT D-01.

Constraints honoured:
    DRY  — only place that names the auth cookies + clears them; cookie
           attributes (domain/secure) read from ``settings.auth.*`` —
           same source of truth used by ``_set_auth_cookies``.
    SRP  — pure HTTP cookie wrangling; no auth-domain knowledge.
    No nested-if (verifier-checked: ``grep -cE "^\\s+if .*\\bif\\b"`` == 0).
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import get_settings

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"


def clear_auth_cookies(response: Response) -> None:
    """Delete both session and csrf cookies on the supplied Response.

    Attributes (``domain`` + ``secure``) MUST mirror those used in
    ``auth_routes._set_auth_cookies`` exactly, or the browser silently
    ignores the deletion (RFC 6265 §5.3 step 11). In any production
    deployment with ``COOKIE_DOMAIN`` configured (e.g. ``.example.com``),
    omitting the attributes leaves the session + CSRF cookies alive after
    logout / logout-all / DELETE /api/account — CR-01 fix.

    Caller MUST pass a freshly constructed ``Response`` (not a
    ``Depends``-injected one) — FastAPI drops ``Set-Cookie`` headers from
    the injected response when the route returns an explicit Response.
    See ``auth_routes.logout`` for the canonical pattern (Phase 13-03
    lesson).
    """
    settings = get_settings()
    domain = settings.auth.COOKIE_DOMAIN or None
    secure = settings.auth.COOKIE_SECURE
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        domain=domain,
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        domain=domain,
        secure=secure,
        httponly=False,
        samesite="lax",
    )
