"""Dependency injection providers for FastAPI endpoints (Phase 19 final)."""

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core import jwt_codec
from app.core import services as core_services
from app.core.config import get_settings
from app.core.exceptions import (
    InvalidApiKeyFormatError,
    InvalidApiKeyHashError,
    JwtAlgorithmError,
    JwtExpiredError,
    JwtTamperedError,
)
from app.domain.entities.user import User
from app.domain.repositories.api_key_repository import IApiKeyRepository
from app.domain.repositories.device_fingerprint_repository import (
    IDeviceFingerprintRepository,
)
from app.domain.repositories.rate_limit_repository import IRateLimitRepository
from app.domain.repositories.task_repository import ITaskRepository
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sqlalchemy_api_key_repository import (
    SQLAlchemyApiKeyRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_device_fingerprint_repository import (
    SQLAlchemyDeviceFingerprintRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.services.account_service import AccountService
from app.services.auth import (
    AuthService,
    KeyService,
    RateLimitService,
)
from app.services.free_tier_gate import FreeTierGate
from app.services.task_management_service import TaskManagementService
from app.services.usage_event_writer import UsageEventWriter


# ===========================================================================
# Phase 19 Plan 13 — single namespace Depends chain (D1 + D2 final).
#
# `get_db` is the ONE site that owns Session.close() for the HTTP request
# scope. Every repo / service factory chains off Depends(get_db) (or off
# another factory that already chains off it). FastAPI's per-request dep
# cache shares the same Session across the entire call graph — ONE Session
# per request, closed once in get_db's finally.
#
# Tiger-style: each factory is 1-3 lines (no try/finally except in get_db
# which centralizes the close); flat early-returns; no nested-if.
# ===========================================================================


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session for the HTTP request; close on exit.

    Single source of truth for request-scoped Session lifecycle (D2 lock).
    Every repo / service factory chains off Depends(get_db); FastAPI shares
    the yielded Session across all sub-deps via its per-request dep cache,
    so the whole route call graph runs on ONE Session that is closed
    exactly once in this finally.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Repository providers — chain off Depends(get_db)
# ---------------------------------------------------------------------------


def get_user_repository(
    db: Session = Depends(get_db),
) -> IUserRepository:
    """Return a SQLAlchemyUserRepository bound to the request-scoped Session."""
    return SQLAlchemyUserRepository(db)


def get_api_key_repository(
    db: Session = Depends(get_db),
) -> IApiKeyRepository:
    """Return a SQLAlchemyApiKeyRepository bound to the request-scoped Session."""
    return SQLAlchemyApiKeyRepository(db)


def get_rate_limit_repository(
    db: Session = Depends(get_db),
) -> IRateLimitRepository:
    """Return a SQLAlchemyRateLimitRepository bound to the request-scoped Session."""
    return SQLAlchemyRateLimitRepository(db)


def get_task_repository(
    db: Session = Depends(get_db),
) -> ITaskRepository:
    """Return an UNSCOPED SQLAlchemyTaskRepository bound to the request Session.

    Per-user scoping (set_user_scope) lives in
    ``get_scoped_task_repository`` which chains off authenticated_user.
    """
    return SQLAlchemyTaskRepository(db)


def get_device_fingerprint_repository(
    db: Session = Depends(get_db),
) -> IDeviceFingerprintRepository:
    """Return a SQLAlchemyDeviceFingerprintRepository bound to the request Session."""
    return SQLAlchemyDeviceFingerprintRepository(db)


# ---------------------------------------------------------------------------
# Service providers — chain off repo providers or core_services singletons
# ---------------------------------------------------------------------------


def get_auth_service(
    user_repository: IUserRepository = Depends(get_user_repository),
) -> AuthService:
    """Return an AuthService wired to the request-scoped user repo + singletons."""
    return AuthService(
        user_repository=user_repository,
        password_service=core_services.get_password_service(),
        token_service=core_services.get_token_service(),
    )


def get_key_service(
    repository: IApiKeyRepository = Depends(get_api_key_repository),
) -> KeyService:
    """Return a KeyService wired to the request-scoped api_key repo."""
    return KeyService(repository=repository)


def get_rate_limit_service(
    repository: IRateLimitRepository = Depends(get_rate_limit_repository),
) -> RateLimitService:
    """Return a RateLimitService wired to the request-scoped rate_limit repo."""
    return RateLimitService(repository=repository)


def get_free_tier_gate(
    rate_limit_service: RateLimitService = Depends(get_rate_limit_service),
) -> FreeTierGate:
    """Return a FreeTierGate wired to the request-scoped RateLimitService."""
    return FreeTierGate(rate_limit_service=rate_limit_service)


def get_usage_event_writer(
    db: Session = Depends(get_db),
) -> UsageEventWriter:
    """Return a UsageEventWriter bound to the request-scoped Session."""
    return UsageEventWriter(session=db)


def get_account_service(
    db: Session = Depends(get_db),
    user_repository: IUserRepository = Depends(get_user_repository),
) -> AccountService:
    """Return an AccountService bound to the request Session + explicit user repo.

    Plan 15-03 deviation lock: AccountService accepts both ``session`` and
    an optional pre-built ``user_repository``; passing both keeps a single
    repo instance shared across methods (DRY) instead of lazy-constructing
    one.
    """
    return AccountService(session=db, user_repository=user_repository)


# ===========================================================================
# Phase 19 Plan 04 — authenticated_user Depends chain (D2)
#
# Owns per-route auth (the legacy middleware was deleted in Plan 11).
# Bearer wins when both presented (CONTEXT §50 invariant). Cookie path
# performs sliding refresh by stamping a fresh Set-Cookie BEFORE the dep
# returns (FastAPI flushes Response headers AFTER route handler runs, so
# the slide must happen during dep resolution, not after).
#
# Subtype-first error tuples mirror the legacy auth-helper resolver —
# specific JWT subtypes caught before generic ValueError. Cookie attrs in
# the slide are byte-identical to the prior implementation (REFACTOR-07
# lock; verified at every commit by tests/integration/test_set_cookie_attrs.py).
#
# Tiger-style: flat early-returns; subtype-first exception tuples; zero
# nested-if (verifier grep returns 0 in this region).
# ===========================================================================


SESSION_COOKIE = "session"
BEARER_PREFIX = "Bearer "
_BEARER_FAILURES = (InvalidApiKeyFormatError, InvalidApiKeyHashError)
_COOKIE_DECODE_FAILURES = (
    JwtExpiredError,
    JwtAlgorithmError,
    JwtTamperedError,
    KeyError,
    ValueError,
)
_COOKIE_REFRESH_FAILURES = (JwtExpiredError, JwtAlgorithmError, JwtTamperedError)
STATE_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _resolve_bearer(plaintext: str, db: Session) -> User | None:
    """Resolve a presented bearer plaintext to a User, or None on failure.

    Two-query semantics carried forward verbatim from the legacy resolver
    (Phase 20 collapses to a single JOIN; preserved here so structural
    refactor and perf optimisation revert independently). Subtype-first
    try/except over _BEARER_FAILURES; any other exception bubbles (caller
    treats as 500).
    """
    key_service = KeyService(repository=SQLAlchemyApiKeyRepository(db))
    try:
        api_key = key_service.verify_plaintext(plaintext)
    except _BEARER_FAILURES:
        return None
    return SQLAlchemyUserRepository(db).get_by_id(api_key.user_id)


def _resolve_cookie(token: str, db: Session, response: Response) -> User | None:
    """Resolve a session-cookie JWT to a User and stamp a sliding-refresh cookie.

    Semantics carried forward from the deleted legacy auth resolver:
      - jwt_codec.decode_session validates HS256 + extracts ``sub``.
      - SQLAlchemyUserRepository.get_by_id loads the user (None → 401 leg).
      - TokenService.verify_and_refresh re-validates the token_version and
        issues a fresh JWT (sliding 7d expiry).
      - response.set_cookie stamps the fresh JWT BEFORE the dep returns so
        FastAPI flushes it on the response (Pitfall 1 in 19-RESEARCH).
      - Cookie attrs byte-identical to the prior implementation
        (REFACTOR-07 — covered by tests/integration/test_set_cookie_attrs.py).

    Returns None on any failure leg — caller decides 401-vs-anonymous.
    """
    settings = get_settings()
    secret = settings.auth.JWT_SECRET.get_secret_value()
    try:
        payload = jwt_codec.decode_session(token, secret=secret)
        user_id = int(payload["sub"])
    except _COOKIE_DECODE_FAILURES:
        return None
    user = SQLAlchemyUserRepository(db).get_by_id(user_id)
    if user is None:
        return None
    try:
        _payload, refreshed = core_services.get_token_service().verify_and_refresh(
            token, user.token_version
        )
    except _COOKIE_REFRESH_FAILURES:
        return None
    response.set_cookie(
        key=SESSION_COOKIE,
        value=refreshed,
        max_age=settings.auth.JWT_TTL_DAYS * 24 * 3600,
        httponly=True,
        secure=settings.auth.COOKIE_SECURE,
        samesite="lax",
        path="/",
        domain=settings.auth.COOKIE_DOMAIN or None,
    )
    return user


def _try_resolve(
    request: Request, response: Response, db: Session
) -> User | None:
    """Bearer wins. Then cookie. Then None. Three flat early-returns.

    Bearer-then-cookie order is the Phase 13 invariant (CONTEXT §50). If
    the bearer header is present but malformed, this returns None — it
    does NOT silently fall through to the cookie (T-19-04-06 mitigation;
    see RESEARCH §Pitfall 5).
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith(BEARER_PREFIX):
        plaintext = auth_header[len(BEARER_PREFIX):].strip()
        return _resolve_bearer(plaintext, db)
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return _resolve_cookie(cookie, db, response)
    return None


async def authenticated_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user via Depends — raise 401 on failure.

    Single 401 detail string ``"Authentication required"`` plus a
    ``Bearer realm="whisperx"`` challenge header preserves the historical
    response shape (T-13-05 anti-leak: callers cannot distinguish which
    auth leg failed).
    """
    user = _try_resolve(request, response, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Bearer realm="whisperx"'},
        )
    return user


async def authenticated_user_optional(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User | None:
    """Same as authenticated_user but returns None instead of raising.

    Used by public routes that need optional auth context (none today;
    placeholder for Plan 16 PUBLIC_ALLOWLIST removal — public routes
    that want to surface user.id when present can opt in via this dep).
    """
    return _try_resolve(request, response, db)


def get_scoped_task_repository(
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> ITaskRepository:
    """Return a per-user-scoped SQLAlchemyTaskRepository.

    Chains off authenticated_user (so anonymous callers 401 before the
    repo is built). No try/finally for session.close — get_db owns the
    request-scoped Session lifecycle (single close site invariant).
    """
    repository = SQLAlchemyTaskRepository(db)
    repository.set_user_scope(int(user.id) if user.id is not None else 0)
    return repository


def get_task_management_service(
    repository: ITaskRepository = Depends(get_scoped_task_repository),
) -> TaskManagementService:
    """Return a TaskManagementService wrapping the user-scoped task repo."""
    return TaskManagementService(repository=repository)


# ===========================================================================
# Phase 19 Plan 05 — csrf_protected Depends factory (D4)
#
# Per-router CSRF dep. Replaced the legacy CSRF middleware (deleted in
# Plan 19-12). Composes with authenticated_user — auth resolves first
# (FastAPI Depends order), CSRF check runs second. Bearer auth bypasses
# (Authorization: Bearer prefix detected before cookie check).
#
# Tiger-style: four flat early-returns / raises; zero nested-if; cookie /
# header tokens use self-explanatory names (cookie_token, header_token).
# csrf_service accessed via the module-level lru-cache singleton in
# app.core.services — single source per the D1 lock.
# ===========================================================================


def csrf_protected(
    request: Request,
    user: User = Depends(authenticated_user),  # auth runs first (DRT)
) -> None:
    """Enforce CSRF double-submit on cookie-auth state-mutating requests.

    Mirrors the legacy middleware semantics 1:1 (verifier-checked by
    tests/integration/test_csrf_protected_dep.py — 5 cases):
        - GET / HEAD / OPTIONS         -> early-return (no CSRF check)
        - Authorization: Bearer ...    -> early-return (bearer skips CSRF)
        - cookie-auth state-mutating
          - X-CSRF-Token absent        -> 403 "CSRF token missing"
          - X-CSRF-Token != csrf cookie-> 403 "CSRF token mismatch"
          - X-CSRF-Token == csrf cookie-> return None (request proceeds)

    The two distinct 403 detail strings ("CSRF token missing" / "CSRF
    token mismatch") match Phase 16 test_csrf_enforcement assertions —
    do NOT collapse to a single string.
    """
    if request.method not in STATE_MUTATING_METHODS:
        return
    if request.headers.get("authorization", "").startswith(BEARER_PREFIX):
        return
    cookie_token = request.cookies.get("csrf_token", "")
    header_token = request.headers.get("x-csrf-token", "")
    if not header_token:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    if not core_services.get_csrf_service().verify(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="CSRF token mismatch")
