"""Dependency injection providers for FastAPI endpoints."""

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.constants import CONTAINER_NOT_INITIALIZED_ERROR
from app.core import jwt_codec
from app.core import services as core_services
from app.core.config import get_settings
from app.core.container import Container
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
from app.domain.services.alignment_service import IAlignmentService
from app.domain.services.diarization_service import IDiarizationService
from app.domain.services.speaker_assignment_service import ISpeakerAssignmentService
from app.domain.services.transcription_service import ITranscriptionService
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
    CsrfService,
    KeyService,
    RateLimitService,
)
from app.services.file_service import FileService
from app.services.free_tier_gate import FreeTierGate
from app.services.task_management_service import TaskManagementService
from app.services.usage_event_writer import UsageEventWriter


# Global container instance - will be set by main.py
_container: Container | None = None


def set_container(container: Container) -> None:
    """Set the global container instance."""
    global _container
    _container = container


def get_task_repository() -> Generator[ITaskRepository, None, None]:
    """
    Provide a task repository implementation for dependency injection.

    Yields a repository bound to a fresh DB session and closes that session
    when the request ends. Without the finally close, every request leaks
    one connection — after pool_size + max_overflow (default 5+10=15) the
    next checkout blocks for 30s before raising, surfacing as a deceptive
    401 because SQLAlchemyError is swallowed downstream.

    Yields:
        ITaskRepository: A task repository implementation
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    repository: ITaskRepository = _container.task_repository()
    try:
        yield repository
    finally:
        repository.session.close()  # type: ignore[attr-defined]


def get_file_service() -> Generator[FileService, None, None]:
    """
    Provide a FileService instance for dependency injection.

    FileService is stateless and registered as a singleton in the container,
    so the same instance is reused across all requests.

    Yields:
        FileService: A file service instance
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    yield _container.file_service()


def get_task_management_service() -> Generator[TaskManagementService, None, None]:
    """
    Provide a TaskManagementService instance for dependency injection.

    Closes the underlying repository session in the finally clause to
    prevent connection-pool exhaustion (see get_task_repository docstring
    for the failure mode).

    Yields:
        TaskManagementService: A task management service instance
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    service: TaskManagementService = _container.task_management_service()
    try:
        yield service
    finally:
        service.repository.session.close()  # type: ignore[attr-defined]


def get_transcription_service() -> Generator[ITranscriptionService, None, None]:
    """
    Provide a transcription service implementation for dependency injection.

    Returns WhisperX implementation from the container. Registered as a singleton
    for model caching and reuse. Can be overridden for testing by using
    container.override_providers().

    Yields:
        ITranscriptionService: A transcription service implementation

    Example:
        >>> @router.post("/transcribe")
        >>> async def transcribe(
        ...     transcription: ITranscriptionService = Depends(get_transcription_service)
        ... ):
        ...     result = transcription.transcribe(audio, params)
        ...     return result
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    yield _container.transcription_service()


def get_diarization_service() -> Generator[IDiarizationService, None, None]:
    """
    Provide a diarization service implementation for dependency injection.

    Returns WhisperX/PyAnnote implementation from the container. Registered as
    a singleton for model caching and reuse. Can be overridden for testing
    by using container.override_providers().

    Yields:
        IDiarizationService: A diarization service implementation

    Example:
        >>> @router.post("/diarize")
        >>> async def diarize(
        ...     diarization: IDiarizationService = Depends(get_diarization_service)
        ... ):
        ...     result = diarization.diarize(audio, device)
        ...     return result
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    yield _container.diarization_service()


def get_alignment_service() -> Generator[IAlignmentService, None, None]:
    """
    Provide an alignment service implementation for dependency injection.

    Returns WhisperX implementation from the container. Registered as a singleton
    for model caching and reuse. Can be overridden for testing by using
    container.override_providers().

    Yields:
        IAlignmentService: An alignment service implementation

    Example:
        >>> @router.post("/align")
        >>> async def align(
        ...     alignment: IAlignmentService = Depends(get_alignment_service)
        ... ):
        ...     result = alignment.align(transcript, audio, language)
        ...     return result
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    yield _container.alignment_service()


def get_speaker_assignment_service() -> Generator[
    ISpeakerAssignmentService, None, None
]:
    """
    Provide a speaker assignment service implementation for dependency injection.

    Returns WhisperX implementation from the container. Registered as a singleton
    for consistency. Can be overridden for testing by using
    container.override_providers().

    Yields:
        ISpeakerAssignmentService: A speaker assignment service implementation

    Example:
        >>> @router.post("/assign-speakers")
        >>> async def assign_speakers(
        ...     speaker_service: ISpeakerAssignmentService = Depends(get_speaker_assignment_service)
        ... ):
        ...     result = speaker_service.assign_speakers(diarization, transcript)
        ...     return result
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    yield _container.speaker_assignment_service()


# ---------------------------------------------------------------
# Phase 13 — legacy request.state auth helpers (deprecated)
#
# request.state.{user, plan_tier, auth_method, api_key_id} was historically
# populated by the legacy auth middleware (deleted in Phase 19-11). These
# helpers remain for the few v1.1 routes that still consume request.state;
# Phase-13+ routes go through ``authenticated_user`` Depends instead (single
# resolution point, DRY). Plan 19-13 removes the last v1.1 callers.
# ---------------------------------------------------------------


def get_authenticated_user(request: Request) -> User:
    """Resolve the authenticated user from request.state.

    Historically the legacy middleware populated ``request.state.user`` on
    every authenticated request; with Phase 19 the population happens via
    ``authenticated_user`` Depends instead. Defence-in-depth raises 401 if
    the helper is reached with ``user is None``.
    """
    user: User | None = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def get_current_user_id(request: Request) -> int:
    """Convenience wrapper returning ``request.state.user.id`` as int."""
    user = get_authenticated_user(request)
    return int(user.id)  # type: ignore[arg-type]


def get_csrf_service() -> CsrfService:
    """Provide the singleton CsrfService for routes issuing CSRF tokens.

    CsrfService is stateless (no DB session); container registers it as a
    Singleton so plain return is safe — no lifecycle to manage.
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    return _container.csrf_service()


def get_key_service() -> Generator[KeyService, None, None]:
    """Provide a per-request KeyService bound to a managed DB session.

    The container Factory chain (key_service → api_key_repository →
    db_session_factory) creates a fresh Session per request. Without the
    finally close, every request leaks one connection — after pool_size
    + max_overflow (default 5+10=15) the next checkout blocks for 30s
    before raising QueuePool timeout. The error is silently swallowed by
    SQLAlchemyUserRepository.get_by_email and surfaces as a deceptive
    401 Invalid credentials.
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    service: KeyService = _container.key_service()
    try:
        yield service
    finally:
        service.repository.session.close()  # type: ignore[attr-defined]


def get_auth_service() -> Generator[AuthService, None, None]:
    """Provide a per-request AuthService bound to a managed DB session.

    Closes the user_repository's Session in the finally clause to
    prevent connection-pool exhaustion (see get_key_service docstring
    for the exhaustion mechanism).
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    service: AuthService = _container.auth_service()
    try:
        yield service
    finally:
        service.user_repository.session.close()  # type: ignore[attr-defined]


def get_rate_limit_service() -> Generator[RateLimitService, None, None]:
    """Provide a per-request RateLimitService bound to a managed DB session.

    Closes the rate_limit_repository's Session in the finally clause to
    prevent connection-pool exhaustion (see get_key_service docstring
    for the exhaustion mechanism).
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    service: RateLimitService = _container.rate_limit_service()
    try:
        yield service
    finally:
        service.repository.session.close()  # type: ignore[attr-defined]


# ---------------------------------------------------------------
# Phase 13-07 — Per-user scoped task repository / task service
#
# Every HTTP route touching `tasks` MUST consume one of these helpers
# instead of get_task_repository / get_task_management_service.
# The auth dep populates request.state.user; we resolve user.id and
# call repo.set_user_scope(user.id) before yielding so every read+write
# is automatically WHERE user_id = caller.
#
# Cross-user requests naturally return None / [] / False at the SQL
# layer — routes raise 404 opaquely (no enumeration).
#
# DRT: scope-setting is owned in one place (these functions); routes
# never repeat the pattern. SCOPE-02..04.
# ---------------------------------------------------------------


def _resolve_authenticated_user_id(request: Request) -> int:
    """Tiger-style guard: extract user.id or 401.

    The auth dep should have already 401'd unauthenticated callers on
    protected paths — this is defence-in-depth (T-13-33).
    """
    user: User | None = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return int(user.id)  # type: ignore[arg-type]


def get_scoped_task_repository(
    request: Request,
) -> Generator[ITaskRepository, None, None]:
    """Yield a task repository scoped to ``request.state.user.id``.

    Calls ``repository.set_user_scope(user.id)`` before yielding; every
    read/write the route performs is automatically filtered to caller's
    rows. The finally clause clears the scope (defence-in-depth in case
    the Factory provider gets pooled in a future refactor).
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    user_id = _resolve_authenticated_user_id(request)
    repository: ITaskRepository = _container.task_repository()
    repository.set_user_scope(user_id)
    try:
        yield repository
    finally:
        repository.set_user_scope(None)
        repository.session.close()  # type: ignore[attr-defined]


def get_scoped_task_management_service(
    request: Request,
) -> Generator[TaskManagementService, None, None]:
    """Yield a TaskManagementService whose underlying repo is user-scoped.

    Same scope contract as get_scoped_task_repository — the wrapped
    service delegates to a repo with set_user_scope(user.id) already
    applied. Used by task_api.py routes that operate via the service
    layer (get/list/delete/progress).
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    user_id = _resolve_authenticated_user_id(request)
    repository: ITaskRepository = _container.task_repository()
    repository.set_user_scope(user_id)
    service = TaskManagementService(repository=repository)
    try:
        yield service
    finally:
        repository.set_user_scope(None)
        repository.session.close()  # type: ignore[attr-defined]


def get_db_session() -> Generator[Session, None, None]:
    """Yield a managed DB session for non-repository scoped reads/writes.

    Used by services that need a raw SQLAlchemy session (e.g. AccountService
    bulk DELETE) rather than a repository wrapper. Session is closed on exit.
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    session = _container.db_session_factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------
# Phase 13-08 — Free-tier gate + usage event writer dependencies
#
# Free-tier gate is wired into transcribe routes BEFORE BackgroundTask
# scheduling. Usage event writer + FreeTierGate.release_concurrency are
# called from process_audio_common's completion try/finally (W1).
# ---------------------------------------------------------------


def get_free_tier_gate() -> Generator[FreeTierGate, None, None]:
    """Provide a per-request FreeTierGate (factory; binds fresh
    RateLimitService -> fresh repo -> fresh DB session).

    Closes the underlying rate_limit_repository's Session in the finally
    clause to prevent connection-pool exhaustion (see get_key_service
    docstring for the exhaustion mechanism).
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    gate: FreeTierGate = _container.free_tier_gate()
    try:
        yield gate
    finally:
        gate.rate_limit_service.repository.session.close()  # type: ignore[attr-defined]


def get_usage_event_writer() -> Generator[UsageEventWriter, None, None]:
    """Provide a per-request UsageEventWriter (factory; fresh DB session).

    Closes the writer's Session in the finally clause to prevent
    connection-pool exhaustion (see get_key_service docstring for the
    exhaustion mechanism).
    """
    if _container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    writer: UsageEventWriter = _container.usage_event_writer()
    try:
        yield writer
    finally:
        writer.session.close()


# ===========================================================================
# Phase 19 v2 providers (Depends chain)
#
# T-19-03 — get_db is the ONE site that owns Session.close() for the HTTP
# request scope. Every `_v2` repo / service factory chains off Depends(get_db)
# (or off another `_v2` provider that already chains off it). FastAPI's
# per-request dep cache shares the same Session across the entire call
# graph — ONE Session per request, closed once in get_db's finally.
#
# Coexistence: existing `_container.X()` providers above stay UNTOUCHED.
# Plans 06-09 migrate routes one wave at a time off the legacy paths;
# Plans 11-13 delete the legacy helpers + container.py once nothing imports
# them. Until then the suffix `_v2` disambiguates new from old.
#
# Tiger-style: each helper is 1-3 lines (factory); no nested-if; only
# get_db has try/finally (the centralized close site).
# ===========================================================================


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session for the HTTP request; close on exit.

    Single source of truth for request-scoped Session lifecycle (D2 lock).
    Every Phase 19 `_v2` repo / service factory chains off
    Depends(get_db); FastAPI shares the yielded Session across all sub-deps
    via its per-request dep cache, so the whole route call graph runs on
    ONE Session that is closed exactly once in this finally.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Repository providers — chain off Depends(get_db)
# ---------------------------------------------------------------------------


def get_user_repository_v2(
    db: Session = Depends(get_db),
) -> IUserRepository:
    """Return a SQLAlchemyUserRepository bound to the request-scoped Session."""
    return SQLAlchemyUserRepository(db)


def get_api_key_repository_v2(
    db: Session = Depends(get_db),
) -> IApiKeyRepository:
    """Return a SQLAlchemyApiKeyRepository bound to the request-scoped Session."""
    return SQLAlchemyApiKeyRepository(db)


def get_rate_limit_repository_v2(
    db: Session = Depends(get_db),
) -> IRateLimitRepository:
    """Return a SQLAlchemyRateLimitRepository bound to the request-scoped Session."""
    return SQLAlchemyRateLimitRepository(db)


def get_task_repository_v2(
    db: Session = Depends(get_db),
) -> ITaskRepository:
    """Return an UNSCOPED SQLAlchemyTaskRepository bound to the request Session.

    Per-user scoping (set_user_scope) lives in Plan 04's
    `get_scoped_task_repository_v2` helper which chains off authenticated_user.
    """
    return SQLAlchemyTaskRepository(db)


def get_device_fingerprint_repository_v2(
    db: Session = Depends(get_db),
) -> IDeviceFingerprintRepository:
    """Return a SQLAlchemyDeviceFingerprintRepository bound to the request Session."""
    return SQLAlchemyDeviceFingerprintRepository(db)


# ---------------------------------------------------------------------------
# Service providers — chain off `_v2` repo providers or core_services singletons
# ---------------------------------------------------------------------------


def get_auth_service_v2(
    user_repository: IUserRepository = Depends(get_user_repository_v2),
) -> AuthService:
    """Return an AuthService wired to the request-scoped user repo + singletons."""
    return AuthService(
        user_repository=user_repository,
        password_service=core_services.get_password_service(),
        token_service=core_services.get_token_service(),
    )


def get_key_service_v2(
    repository: IApiKeyRepository = Depends(get_api_key_repository_v2),
) -> KeyService:
    """Return a KeyService wired to the request-scoped api_key repo."""
    return KeyService(repository=repository)


def get_rate_limit_service_v2(
    repository: IRateLimitRepository = Depends(get_rate_limit_repository_v2),
) -> RateLimitService:
    """Return a RateLimitService wired to the request-scoped rate_limit repo."""
    return RateLimitService(repository=repository)


def get_free_tier_gate_v2(
    rate_limit_service: RateLimitService = Depends(get_rate_limit_service_v2),
) -> FreeTierGate:
    """Return a FreeTierGate wired to the request-scoped RateLimitService."""
    return FreeTierGate(rate_limit_service=rate_limit_service)


def get_usage_event_writer_v2(
    db: Session = Depends(get_db),
) -> UsageEventWriter:
    """Return a UsageEventWriter bound to the request-scoped Session."""
    return UsageEventWriter(session=db)


def get_account_service_v2(
    db: Session = Depends(get_db),
    user_repository: IUserRepository = Depends(get_user_repository_v2),
) -> AccountService:
    """Return an AccountService bound to the request Session + explicit user repo.

    Plan 15-03 deviation lock: AccountService accepts both `session` and an
    optional pre-built `user_repository`; passing both keeps a single repo
    instance shared across methods (DRY) instead of lazy-constructing one.
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
# Public routes (e.g. /auth/login, /health) either omit the dep or use
# authenticated_user_optional — the legacy public allowlist is gone with
# the middleware (Plan 16 finalises the dead-code sweep).
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


def get_scoped_task_repository_v2(
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


def get_task_management_service_v2(
    repository: ITaskRepository = Depends(get_scoped_task_repository_v2),
) -> TaskManagementService:
    """Return a TaskManagementService wrapping the user-scoped task repo."""
    return TaskManagementService(repository=repository)


# ===========================================================================
# Phase 19 Plan 05 — csrf_protected Depends factory (D4)
#
# Per-router CSRF dep. Replaced the legacy middleware (deleted in Plan 19-12).
# Composes with authenticated_user — auth resolves first (FastAPI Depends
# order), CSRF check runs second. Bearer auth bypasses (Authorization: Bearer
# prefix detected before cookie check).
#
# Tiger-style: four flat early-returns / raises; zero nested-if; cookie /
# header tokens use self-explanatory names (cookie_token, header_token).
# csrf_service accessed via the module-level lru-cache singleton (NOT the
# legacy DI container) — single source per the D1 lock.
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
