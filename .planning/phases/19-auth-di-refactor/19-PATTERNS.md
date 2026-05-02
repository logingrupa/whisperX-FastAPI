# Phase 19: Auth + DI Structural Refactor — Pattern Map

**Mapped:** 2026-05-02
**Files analyzed:** 27 (3 NEW + 24 MODIFIED/DELETED)
**Analogs found:** 25 / 27 (2 files have no analog — DEVIATIONS.md already exists; new no-leak test pattern)

## File Classification

| File | Action | Role | Data Flow | Closest Analog | Match Quality |
|------|--------|------|-----------|----------------|---------------|
| `app/core/services.py` | NEW | config / singleton-factory | none (lazy init) | `app/core/rate_limiter.py` (module-level singleton) + `app/infrastructure/database/connection.py` (engine + SessionLocal) | role-match (no `@lru_cache` analog yet — first-use in app) |
| `tests/integration/test_no_session_leak.py` | NEW | test (integration, perf gate) | sequential request-response | `tests/integration/test_argon2_benchmark.py` (50-loop perf gate) + `scripts/verify_session_leak_fix.py` (drain-30 pattern) | role-match |
| `.planning/DEVIATIONS.md` | NEW (already created) | doc | n/a | n/a (already on disk; first entry committed) | n/a |
| `app/api/dependencies.py` | REWRITE | provider / FastAPI Depends | request-response | EXISTING `get_db_session` (lines 366-378) + `get_scoped_task_repository` (lines 321-340) — both already use yield/finally close | exact (idiom present in same file) |
| `app/api/auth_routes.py` | MODIFIED | controller | request-response | EXISTING `app/api/auth_routes.py` itself (lines 39-43, 117-180) — only swap `get_authenticated_user` → `authenticated_user`, keep `request: Request` for slowapi | exact |
| `app/api/account_routes.py` | MODIFIED | controller | request-response | EXISTING `app/api/account_routes.py` (lines 38-47, 50-58) — pattern is correct; only dep names change | exact |
| `app/api/key_routes.py` | MODIFIED | controller | CRUD | EXISTING `app/api/key_routes.py` (lines 14-18, 43-49) — only dep names change | exact |
| `app/api/billing_routes.py` | MODIFIED | controller | request-response | EXISTING `app/api/billing_routes.py` (lines 31, 51-54) — single-dep swap | exact |
| `app/api/task_api.py` | MODIFIED | controller | CRUD | `app/api/key_routes.py` (Depends-chain shape) | exact (same router style) |
| `app/api/ws_ticket_routes.py` | MODIFIED | controller | request-response (HTTP issuing WS ticket) | self (lines 60-99) — replace inline `get_ws_ticket_service` (lines 43-57) with import from `app.core.services` | exact |
| `app/api/websocket_api.py` | REWRITE | controller (WS scope) | streaming | self (lines 52-89) + RESEARCH §Pattern Example 2 (`with SessionLocal() as db:` block) | role-match |
| `app/main.py` | MODIFIED | bootstrap / config | n/a | self (lines 70-262) — surgical deletions only | exact |
| `app/core/dual_auth.py` | DELETE | middleware | request-response | n/a (deleted) | — |
| `app/core/csrf_middleware.py` | DELETE | middleware | request-response | the new `csrf_protected` Depends in `dependencies.py` mirrors lines 52-69 logic | role-match |
| `app/core/auth.py` (BearerAuthMiddleware) | DELETE | middleware | request-response | n/a (deleted) | — |
| `app/core/container.py` | DELETE | DI graph | n/a | n/a (deleted) | — |
| `app/core/feature_flags.py` (`is_auth_v2_enabled`) | MODIFIED (helper removed) | config | n/a | self | exact |
| `app/services/whisperx_wrapper_service.py` | MODIFIED (background block) | service / worker | event-driven (BackgroundTask) | EXISTING `app/infrastructure/database/connection.py:62-66` (`with engine.connect() as _verify_conn`) — context-manager pattern | role-match |
| `tests/conftest.py` | MODIFIED | fixture | n/a | self (lines 49-70) — replace `test_container` fixture with autouse `_clear_overrides` + `_clear_lru_caches` | role-match |
| `tests/fixtures/test_container.py` | DELETE | fixture | n/a | n/a (deleted) | — |
| `tests/fixtures/database.py` | UNCHANGED reference | fixture | n/a | self (lines 13-49) — the `test_db_engine` + `db_session` shape is the migration target | exact |
| 14 integration test files | MIGRATED | test fixtures | request-response | `tests/integration/test_account_routes.py:55-117` (current `account_app` fixture) → migrate to `app.dependency_overrides[get_db]` shape | role-match |

---

## Pattern Assignments

### `app/core/services.py` (NEW — module-level @lru_cache singletons)

**Closest analog 1:** `app/core/rate_limiter.py` — module-level Singleton idiom in this codebase.

**Why this analog:** the file already proves the project's "single source of truth" pattern for stateless services without `dependency-injector`.

**Singleton pattern to mirror** (`app/core/rate_limiter.py:64-68`):
```python
# Module-level singleton — used by `@limiter.limit("3/hour")` decorators on
# /auth/register, /auth/login, etc. App wiring (mounting limiter onto
# `app.state.limiter`) lives in plan 13-09.
limiter = Limiter(key_func=_client_subnet_key, default_limits=[])
```

**Closest analog 2:** `app/infrastructure/database/connection.py:27-29, 59` — the engine + `SessionLocal` are also module-level singletons, accessed via direct import.

```python
DB_URL = Config.DB_URL
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
# ...
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

**Phase 19 form** (per RESEARCH.md §Q3 — `@lru_cache(maxsize=1)` factories, NOT bare globals):
```python
# app/core/services.py — NEW FILE

from functools import lru_cache

from app.core.config import get_settings
from app.services.auth.csrf_service import CsrfService
from app.services.auth.password_service import PasswordService
from app.services.auth.token_service import TokenService
from app.services.ws_ticket_service import WsTicketService


@lru_cache(maxsize=1)
def get_password_service() -> PasswordService:
    return PasswordService()


@lru_cache(maxsize=1)
def get_csrf_service() -> CsrfService:
    return CsrfService()


@lru_cache(maxsize=1)
def get_token_service() -> TokenService:
    return TokenService(
        secret=get_settings().auth.JWT_SECRET.get_secret_value(),
    )


@lru_cache(maxsize=1)
def get_ws_ticket_service() -> WsTicketService:
    return WsTicketService()


# ML services — lazy-import inside factory to keep CLI/migration paths
# free of model-load side effects (RESEARCH §Open Question 1).
@lru_cache(maxsize=1)
def get_transcription_service():
    from app.infrastructure.ml import WhisperXTranscriptionService
    return WhisperXTranscriptionService()
```

**Tiger-style compliance:** zero nested-if; one factory per service; lazy import for ML keeps non-ML paths fast.

---

### `app/api/dependencies.py` (REWRITE — replaces 16 `_container.X()` callsites)

**Closest analog (in same file):** `get_db_session` lines 366-378 + `get_scoped_task_repository` lines 321-340. Both already use yield/finally + close. Mirror this idiom for ALL providers.

**Existing yield/finally close idiom** (`app/api/dependencies.py:366-378`):
```python
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
```

**Existing scoped-repo idiom (the goal shape, sans `_container`)** (`app/api/dependencies.py:321-340`):
```python
def get_scoped_task_repository(
    request: Request,
) -> Generator[ITaskRepository, None, None]:
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
```

**Phase 19 final shape** (RESEARCH §Pattern 1-5):
```python
# app/api/dependencies.py — Phase 19

def get_db() -> Generator[Session, None, None]:
    """ONE place that owns Session.close(). Every other dep chains off this."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user_repository(db: Session = Depends(get_db)) -> IUserRepository:
    return SQLAlchemyUserRepository(db)


def get_api_key_repository(db: Session = Depends(get_db)) -> IApiKeyRepository:
    return SQLAlchemyApiKeyRepository(db)


def get_auth_service(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(
        user_repository=user_repo,
        password_service=services.get_password_service(),  # @lru_cache
        token_service=services.get_token_service(),
    )


def get_scoped_task_repository(
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> ITaskRepository:
    repo = SQLAlchemyTaskRepository(db)
    repo.set_user_scope(int(user.id))
    return repo  # NO try/finally — get_db's finally closes the shared Session
```

**Auth pattern** (replaces `DualAuthMiddleware._resolve_bearer/_resolve_cookie`, mirroring `app/core/dual_auth.py:194-276`):
```python
SESSION_COOKIE = "session"
BEARER_PREFIX = "Bearer "
_BEARER_FAILURES = (InvalidApiKeyFormatError, InvalidApiKeyHashError)
_COOKIE_DECODE_FAILURES = (
    JwtExpiredError, JwtAlgorithmError, JwtTamperedError, KeyError, ValueError,
)


def _resolve_bearer(plaintext: str, db: Session) -> User | None:
    """Two-query path verbatim from dual_auth.py:209-225 (Phase 20 collapses)."""
    key_service = KeyService(repository=SQLAlchemyApiKeyRepository(db))
    try:
        api_key = key_service.verify_plaintext(plaintext)
    except _BEARER_FAILURES:
        return None
    return SQLAlchemyUserRepository(db).get_by_id(api_key.user_id)


def _resolve_cookie(token: str, db: Session, response: Response) -> User | None:
    secret = get_settings().auth.JWT_SECRET.get_secret_value()
    try:
        payload = jwt_codec.decode_session(token, secret=secret)
        user_id = int(payload["sub"])
    except _COOKIE_DECODE_FAILURES:
        return None
    user = SQLAlchemyUserRepository(db).get_by_id(user_id)
    if user is None:
        return None
    try:
        _payload, refreshed = services.get_token_service().verify_and_refresh(
            token, user.token_version,
        )
    except (JwtExpiredError, JwtAlgorithmError, JwtTamperedError):
        return None
    settings = get_settings()
    response.set_cookie(  # MUST be before the dep returns; see RESEARCH Pitfall 1
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
    request: Request, response: Response, db: Session,
) -> User | None:
    """Bearer wins. Then cookie. Then None. Flat early-returns."""
    auth = request.headers.get("authorization", "")
    if auth.startswith(BEARER_PREFIX):
        return _resolve_bearer(auth[len(BEARER_PREFIX):].strip(), db)
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return _resolve_cookie(cookie, db, response)
    return None


async def authenticated_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    user = _try_resolve(request, response, db)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Bearer realm="whisperx"'},
        )
    return user


async def authenticated_user_optional(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User | None:
    return _try_resolve(request, response, db)
```

**CSRF dep** (replaces `app/core/csrf_middleware.py:52-69`):
```python
STATE_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def csrf_protected(
    request: Request,
    user: User = Depends(authenticated_user),  # auth runs first (DRT)
) -> None:
    if request.method not in STATE_MUTATING_METHODS:
        return  # GET/HEAD/OPTIONS skip
    if request.headers.get("authorization", "").startswith(BEARER_PREFIX):
        return  # bearer skips CSRF
    cookie_token = request.cookies.get("csrf_token", "")
    header_token = request.headers.get("x-csrf-token", "")
    if not header_token:
        raise HTTPException(403, "CSRF token missing")
    if not services.get_csrf_service().verify(cookie_token, header_token):
        raise HTTPException(403, "CSRF token mismatch")
```

**Tiger-style compliance:** flat early-returns; subtype-first error tuples (`_BEARER_FAILURES`, `_COOKIE_DECODE_FAILURES`); zero nested-if.

---

### `app/api/auth_routes.py` (MODIFIED — re-wire deps)

**Analog:** `app/api/auth_routes.py` itself (lines 39-43, 117-180). The route bodies are correct; only the imports and `Depends(...)` names change.

**Imports — current** (lines 39-43):
```python
from app.api.dependencies import (
    get_auth_service,
    get_authenticated_user,
    get_csrf_service,
)
```

**Imports — Phase 19** (only delta is `get_authenticated_user` → `authenticated_user`):
```python
from app.api.dependencies import (
    authenticated_user,        # was: get_authenticated_user
    csrf_protected,            # NEW — applied per-route to /logout-all
    get_auth_service,
)
from app.core.services import get_csrf_service  # was from app.api.dependencies
```

**Slowapi `request: Request` parameter MUST stay** (per RESEARCH Pitfall 5 + auth_routes.py:125):
```python
@auth_router.post("/register", ...)
@limiter.limit("3/hour")
async def register(
    request: Request,           # MUST be first positional arg for slowapi
    response: Response,
    body: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    ...
```

**Per-route CSRF for `/auth/logout-all`** (per RESEARCH Pattern 5 §Wired):
```python
@auth_router.post("/logout-all", dependencies=[Depends(csrf_protected)])
async def logout_all(
    user: User = Depends(authenticated_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    ...
```

---

### `app/api/account_routes.py` (MODIFIED — minimal delta)

**Analog:** self (lines 22-47, 50-58). The shape is already canonical FastAPI; only dep names change.

**Current** (`app/api/account_routes.py:22-47`):
```python
from app.api.dependencies import get_authenticated_user, get_db_session
# ...
def get_account_service(
    session: Session = Depends(get_db_session),
) -> AccountService:
    return AccountService(session=session)


@account_router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_data(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
```

**Phase 19** (rename only — `get_authenticated_user` → `authenticated_user`, `get_db_session` → `get_db`):
```python
from app.api.dependencies import authenticated_user, get_db
# ...
def get_account_service(
    session: Session = Depends(get_db),
) -> AccountService:
    return AccountService(session=session)


@account_router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_data(
    user: User = Depends(authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
```

**Router-level CSRF** (apply once at router declaration):
```python
account_router = APIRouter(
    prefix="/api/account",
    tags=["Account"],
    dependencies=[Depends(csrf_protected)],  # only DELETEs need it; GET /me
                                              # is exempt because csrf_protected
                                              # early-returns on GET method
)
```

---

### `app/api/key_routes.py`, `billing_routes.py`, `task_api.py` (MODIFIED — same pattern)

**Analog for all three:** `app/api/key_routes.py:14-49` — already canonical FastAPI Depends shape.

**Current** (`app/api/key_routes.py:14-49`):
```python
from app.api.dependencies import (
    get_authenticated_user,
    get_auth_service,
    get_key_service,
)

key_router = APIRouter(prefix="/api/keys", tags=["API Keys"])


@key_router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateKeyResponse)
async def create_key(
    body: CreateKeyRequest,
    user: User = Depends(get_authenticated_user),
    key_service: KeyService = Depends(get_key_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> CreateKeyResponse:
```

**Phase 19** (rename + add router-level csrf):
```python
key_router = APIRouter(
    prefix="/api/keys",
    tags=["API Keys"],
    dependencies=[Depends(csrf_protected)],
)
# inside route:
user: User = Depends(authenticated_user),
```

**`task_api.py`** keeps `get_scoped_task_management_service` (RESEARCH Open Q3); only the dep's signature changes (chains off `authenticated_user` instead of reading `request.state.user`).

---

### `app/api/ws_ticket_routes.py` (MODIFIED — drop inline factory)

**Current** (`app/api/ws_ticket_routes.py:43-57, 60-69`) — inline `get_ws_ticket_service` reaches into `_container`:
```python
def get_ws_ticket_service() -> WsTicketService:
    from app.api import dependencies
    if dependencies._container is None:
        raise RuntimeError(CONTAINER_NOT_INITIALIZED_ERROR)
    return dependencies._container.ws_ticket_service()


@ws_ticket_router.post("/ticket", ...)
async def issue_ticket(
    body: TicketRequest,
    user: User = Depends(get_authenticated_user),
    repository: ITaskRepository = Depends(get_scoped_task_repository),
    ticket_service: WsTicketService = Depends(get_ws_ticket_service),
) -> TicketResponse:
```

**Phase 19** — delete inline factory; import from `app.core.services`:
```python
from app.api.dependencies import authenticated_user, get_scoped_task_repository
from app.core.services import get_ws_ticket_service  # @lru_cache singleton

@ws_ticket_router.post("/ticket", ...)
async def issue_ticket(
    body: TicketRequest,
    user: User = Depends(authenticated_user),
    repository: ITaskRepository = Depends(get_scoped_task_repository),
    ticket_service: WsTicketService = Depends(get_ws_ticket_service),
) -> TicketResponse:
```

---

### `app/api/websocket_api.py` (REWRITE — `with SessionLocal() as db:` block)

**Closest analog (in codebase):** `app/infrastructure/database/connection.py:62-66` — the only existing `with engine.connect() as ...` pattern in `app/`. Same context-manager idiom.

```python
# app/infrastructure/database/connection.py:62-66
with engine.connect() as _verify_conn:
    _fk_on = _verify_conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert _fk_on == 1, ...
```

**Current** (`app/api/websocket_api.py:71-89`) — reaches into `_container` + manual close:
```python
from app.api import dependencies

if dependencies._container is None:
    await websocket.close(code=WS_POLICY_VIOLATION)
    return

ticket_service = dependencies._container.ws_ticket_service()
task_repo = dependencies._container.task_repository()
try:
    task = task_repo.get_by_id(task_id)
finally:
    task_repo.session.close()
```

**Phase 19** (RESEARCH §Code Example 2):
```python
from app.core.services import get_ws_ticket_service
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)

if not ticket:
    await websocket.close(code=WS_POLICY_VIOLATION)
    return

ticket_service = get_ws_ticket_service()  # @lru_cache singleton

with SessionLocal() as db:                # short-lived; closes on context exit
    task = SQLAlchemyTaskRepository(db).get_by_id(task_id)
# session is now closed; we have the task entity in memory

if task is None:
    await websocket.close(code=WS_POLICY_VIOLATION)
    return
# ... rest of guards unchanged ...
```

**Tiger-style compliance:** five flat guards preserved verbatim; ZERO `dependencies._container is None` defensive guard (the singleton is always available); ZERO manual `.close()`.

---

### `app/main.py` (MODIFIED — surgical deletions)

**Analog:** self. Three regions to delete (lines verified against current file).

**Region 1: Container() instantiation** (`app/main.py:73-80`) — DELETE entirely:
```python
# DELETE these lines:
container = Container()
from app.api import dependencies
dependencies.set_container(container)
```

**Region 2: AUTH_V2 branch** (`app/main.py:198-208`) — replace 11 lines with zero lines (no auth middleware; auth is per-route Depends):
```python
# BEFORE:
if is_auth_v2_enabled():
    app.add_middleware(CsrfMiddleware, container=container)
    app.add_middleware(DualAuthMiddleware, container=container)
else:
    app.add_middleware(BearerAuthMiddleware)

# AFTER: (block deleted entirely; CORSMiddleware lines 213-221 stay verbatim)
```

**Region 3: AUTH_V2 router gate + prod guard** (`app/main.py:247-262`) — delete the `if is_auth_v2_enabled():` wrapper + the prod-fail guard:
```python
# BEFORE:
if is_auth_v2_enabled():
    app.include_router(auth_router)
    app.include_router(key_router)
    app.include_router(account_router)
    app.include_router(billing_router)
    app.include_router(ws_ticket_router)

if settings.ENVIRONMENT == "production" and not is_auth_v2_enabled():
    raise RuntimeError(...)

# AFTER:
app.include_router(auth_router)
app.include_router(key_router)
app.include_router(account_router)
app.include_router(billing_router)
app.include_router(ws_ticket_router)
```

**Region 4: Imports cleanup** (`app/main.py:45-49, 61`) — remove dead imports:
```python
# DELETE:
from app.core.auth import BearerAuthMiddleware
from app.core.container import Container
from app.core.csrf_middleware import CsrfMiddleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.feature_flags import is_auth_v2_enabled
```

---

### `app/services/whisperx_wrapper_service.py` (MODIFIED — `with SessionLocal() as db:` block)

**Closest analog:** `app/infrastructure/database/connection.py:62-66` (`with engine.connect() as ...`) — same context-manager idiom. NO existing `with SessionLocal() as` block in `app/` today; this is a NEW pattern in the codebase.

**Current pattern** (`app/services/whisperx_wrapper_service.py:293-319, 363-377`) — reaches into `_container` + manual close:
```python
def _resolve_user_for_task(task_user_id: int | None) -> User | None:
    # ...
    from app.api.dependencies import _container
    if _container is None:
        return None
    user_repo = _container.user_repository()
    try:
        return user_repo.get_by_id(task_user_id)
    finally:
        user_repo.session.close()


def process_audio_common(...):
    # ...
    session = SessionLocal()
    repository: ITaskRepository = SQLAlchemyTaskRepository(session)
    # ...
    free_tier_gate = None
    try:
        from app.api.dependencies import _container
        if _container is not None:
            free_tier_gate = _container.free_tier_gate()
            usage_writer = _container.usage_event_writer()
    except Exception as exc:
        logger.warning("DI unavailable: %s", exc)
```

**Phase 19** (RESEARCH §Code Example 3):
```python
def process_audio_common(params, ...):
    with SessionLocal() as db:                 # ONE session for the worker
        repository = SQLAlchemyTaskRepository(db)
        rate_limit_service = RateLimitService(
            repository=SQLAlchemyRateLimitRepository(db),
        )
        free_tier_gate = FreeTierGate(rate_limit_service=rate_limit_service)
        usage_writer = UsageEventWriter(session=db)
        user_repo = SQLAlchemyUserRepository(db)

        try:
            # ... transcription work ...
            transcription_succeeded = True
        except (RuntimeError, ValueError, KeyError) as e:
            transcription_succeeded = False
        finally:
            # W1 contract — release slot on success AND failure
            completed_task = repository.get_by_id(params.identifier)
            if completed_task is not None and completed_task.user_id is not None:
                user = user_repo.get_by_id(completed_task.user_id)
                if user is not None:
                    free_tier_gate.release_concurrency(user)
            # ...
    # context exit — db.close() runs automatically
```

**Tiger-style compliance:** ONE Session per worker run; ZERO `try/finally session.close()`; `_resolve_user_for_task` helper DELETED — the user lookup is inline inside the `with` block where the session is alive.

---

### `tests/integration/test_no_session_leak.py` (NEW — perf regression gate)

**Closest analog 1:** `tests/integration/test_argon2_benchmark.py:25-38` — 100-iteration perf gate with `time.perf_counter`.

**Loop pattern to mirror** (`tests/integration/test_argon2_benchmark.py:25-38`):
```python
@pytest.mark.slow
@pytest.mark.integration
class TestArgon2Benchmark:
    def test_argon2_p99_under_300ms(self) -> None:
        durations_ms: list[float] = []
        for i in range(_ITERATIONS):
            t0 = time.perf_counter()
            password_hasher.hash(f"benchmark-pwd-{i}")
            durations_ms.append((time.perf_counter() - t0) * 1000.0)
        durations_ms.sort()
        p99 = durations_ms[_ITERATIONS - 2]
        assert p99 < _BUDGET_MS, ...
```

**Closest analog 2:** `scripts/verify_session_leak_fix.py:52-71` — 30-iteration drain-loop with per-iter < 100ms gate.

**Phase 19 form** — TestClient sequential + < 100ms per request:
```python
"""tests/integration/test_no_session_leak.py — Phase 19 CI gate (T-19-13).

Pre-fix: iteration ~16 of authed GET /api/account/me hangs 30s on
QueuePool checkout (default pool_size=5 + max_overflow=10 = 15). Fix is
the Phase 19 structural refactor — ONE Session per request via get_db.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

# Fixture imports use the new Phase 19 conftest helpers.
from tests.integration.conftest import client_with_db, register_user

_ITERATIONS = 50
_PER_REQUEST_BUDGET_MS = 100.0


@pytest.mark.integration
class TestNoSessionLeak:
    """50 sequential authed GET /api/account/me MUST each return < 100ms.

    Without get_db's yield/finally close (or with the dropped middleware
    direct-container leak), iter ~16 hangs 30s on QueuePool timeout.
    """

    def test_fifty_sequential_authed_requests_under_budget(
        self, client_with_db: TestClient,
    ) -> None:
        # Boundary assertion (tiger-style): cookies acquired before loop.
        register_user(client_with_db, "leak-test@example.com")
        assert client_with_db.cookies.get("session") is not None

        durations_ms: list[float] = []
        for i in range(_ITERATIONS):
            t0 = time.perf_counter()
            response = client_with_db.get("/api/account/me")
            elapsed = (time.perf_counter() - t0) * 1000.0
            assert response.status_code == 200, (
                f"iter {i}: expected 200, got {response.status_code}"
            )
            assert elapsed < _PER_REQUEST_BUDGET_MS, (
                f"iter {i}: {elapsed:.1f}ms exceeded {_PER_REQUEST_BUDGET_MS}ms "
                f"(suggests pool exhaustion at iter {i})"
            )
            durations_ms.append(elapsed)

        # Tiger-style boundary post-assertion: tail latency healthy.
        durations_ms.sort()
        p95 = durations_ms[int(_ITERATIONS * 0.95)]
        assert p95 < _PER_REQUEST_BUDGET_MS, f"p95={p95:.1f}ms"
```

**Tiger-style compliance:** boundary asserts BEFORE loop (cookie present) and AFTER loop (p95). Flat early-returns inside loop (assert-fast). Self-explanatory names — `_PER_REQUEST_BUDGET_MS`, `client_with_db`.

---

### Test fixture migration: 14 integration files

**Closest analog:** `tests/integration/test_account_routes.py:55-117` — current `account_app` fixture pattern that uses `container.db_session_factory.override(providers.Factory(session_factory))`.

**Current pattern** (`tests/integration/test_account_routes.py:87-111`):
```python
@pytest.fixture
def account_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app: auth_router + account_router + DualAuthMiddleware."""
    container = Container()
    container.db_session_factory.override(providers.Factory(session_factory))
    dependencies.set_container(container)

    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)
    app.include_router(account_router)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()
```

**Phase 19 migration target** (RESEARCH §Code Example 4):
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db
from app.infrastructure.database.models import Base
from app.main import app  # production app — no slim subclass needed


@pytest.fixture
def test_db_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(test_db_engine) -> Generator[TestClient, None, None]:
    TestSession = sessionmaker(autoflush=False, autocommit=False, bind=test_db_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

**Removed in migration:**
- `from dependency_injector import providers`
- `from app.core.container import Container`
- `from app.core.dual_auth import DualAuthMiddleware`
- `container.db_session_factory.override(...)`
- `dependencies.set_container(container)`
- `app.add_middleware(DualAuthMiddleware, container=container)`

**Added in migration:**
- `app.dependency_overrides[get_db] = override_get_db`
- `app.dependency_overrides.clear()` in teardown

---

### `tests/conftest.py` (MODIFIED — autouse cleanup fixtures)

**Analog:** self (lines 49-70) — `test_container` fixture pattern that creates a `TestContainer`. Phase 19 replaces with two autouse cleanup fixtures.

**Current** (`tests/conftest.py:49-70`):
```python
@pytest.fixture(scope="function")
def test_container() -> Generator[TestContainer, None, None]:
    container = TestContainer()
    yield container
```

**Phase 19** (RESEARCH §Pitfall 6 + 7):
```python
@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """Test isolation: prevent overrides bleeding across files (Pitfall 6)."""
    yield
    from app.main import app
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_lru_caches():
    """Test isolation: clear @lru_cache singletons between tests (Pitfall 7)."""
    yield
    from app.core import services
    services.get_password_service.cache_clear()
    services.get_csrf_service.cache_clear()
    services.get_token_service.cache_clear()
    services.get_ws_ticket_service.cache_clear()
```

---

## Shared Patterns (apply to multiple files)

### Pattern A — `Depends` chain off `get_db`

**Source:** `app/api/dependencies.py:366-378` (`get_db_session` — current correct shape; rename to `get_db` for Phase 19)

**Apply to:** ALL repository providers + service providers in `app/api/dependencies.py`

```python
# Repository — chain off get_db
def get_user_repository(db: Session = Depends(get_db)) -> IUserRepository:
    return SQLAlchemyUserRepository(db)

# Service — chain off repo (which chains off get_db)
def get_auth_service(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(
        user_repository=user_repo,
        password_service=services.get_password_service(),
        token_service=services.get_token_service(),
    )
```

**Why this works:** FastAPI caches `Depends(get_db)` per-request — every dep that depends on `get_db` shares ONE Session. Single resolution per request; close once at request end.

**Verifier grep gate:** `grep -rn 'session\.close()' app/` returns ≤ 2 (one in `get_db`, one in `whisperx_wrapper_service.py` for context-manager — actually zero there since `with SessionLocal() as db:` `__exit__` closes implicitly).

---

### Pattern B — `with SessionLocal() as db:` block (non-Depends scope)

**Source:** `app/infrastructure/database/connection.py:62-66` (existing `with engine.connect() as ...` idiom; same shape applied to `SessionLocal()`)

**Apply to:** `app/services/whisperx_wrapper_service.py` (BackgroundTask), `app/api/websocket_api.py` (WS handler)

```python
with SessionLocal() as db:           # short-lived; closes on context exit
    repository = SQLAlchemyTaskRepository(db)
    # ...all DB work inside this block...
# session.close() runs automatically via __exit__ — NO manual close
```

**Why:** Background + WS scopes have NO `Request`, NO `Depends`. The context manager is the SQLAlchemy-native lifecycle owner.

**Anti-pattern to avoid:** passing a `Depends(get_db)` Session into a `BackgroundTask` — it closes when the request finishes, BackgroundTask runs after, gets `DetachedInstanceError`. (RESEARCH Pitfall 2.)

---

### Pattern C — Module-level `@lru_cache(maxsize=1)` singleton

**Source:** `app/core/rate_limiter.py:64-68` (existing module-level singleton — `limiter = Limiter(...)`)

**Apply to:** `app/core/services.py` for stateless services

```python
@lru_cache(maxsize=1)
def get_password_service() -> PasswordService:
    return PasswordService()
```

**Why `@lru_cache` (not bare global):** lazy init (ML services don't load on `import`); test override via `app.dependency_overrides`; explicit `cache_clear()` handle for test teardown.

---

### Pattern D — Subtype-first error tuple

**Source:** `app/core/dual_auth.py:110-125` (existing pattern; preserved verbatim in Phase 19)

```python
_BEARER_FAILURE_EXCEPTIONS = (InvalidApiKeyFormatError, InvalidApiKeyHashError)
_COOKIE_DECODE_EXCEPTIONS = (
    JwtExpiredError, JwtAlgorithmError, JwtTamperedError, KeyError, ValueError,
)
_COOKIE_REFRESH_EXCEPTIONS = (JwtExpiredError, JwtAlgorithmError, JwtTamperedError)
```

**Apply to:** `app/api/dependencies.py` `_resolve_bearer` + `_resolve_cookie` helpers.

**Why:** matches CLAUDE.md's "subtype-first error handling" rule. Specific JWT subtypes caught before generic `ValueError`.

---

### Pattern E — Flat early-return guards (tiger-style, no nested-if)

**Source:** `app/api/websocket_api.py:73-108` — five flat guards already exemplary.

**Apply to:** `_try_resolve`, `csrf_protected`, all new dep functions in Phase 19.

```python
# GOOD (Phase 19 target):
if not ticket:
    await websocket.close(code=WS_POLICY_VIOLATION)
    return
if dependencies._container is None:    # this whole guard goes away in Phase 19
    await websocket.close(code=WS_POLICY_VIOLATION)
    return
# ...

# BAD (forbidden — verifier greps `^\s+if .*\bif\b` returns 0):
if a:
    if b:
        if c:
            ...
```

**Verifier grep:** `grep -cE "^\s+if .*\bif\b" app/api/dependencies.py app/main.py app/core/services.py` returns 0.

---

### Pattern F — Cookie-attribute single source of truth

**Source:** `app/core/dual_auth.py:310-321` (`_set_session_cookie`) + `app/api/_cookie_helpers.py` (locked attrs).

**Apply to:** `_resolve_cookie` in `dependencies.py` — sliding refresh MUST mirror these attrs byte-identical (verification gate REFACTOR-07 via Playwright e2e).

```python
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
```

**Why:** any drift from these attrs breaks Phase 15 e2e (`bun run test:e2e`) which captures Set-Cookie wire bytes.

---

## No Analog Found

| File | Reason |
|------|--------|
| `.planning/DEVIATIONS.md` | Already exists on disk (committed in CONTEXT.md prep, see `git status` — untracked file ready for first commit). No analog needed; plain markdown. |
| `tests/integration/test_no_session_leak.py` | NEW shape — 50-iter authed TestClient loop + per-request budget. Closest analog is `test_argon2_benchmark.py` (100-iter `perf_counter`), but the TestClient cookie-jar interaction is novel. The drain-loop in `scripts/verify_session_leak_fix.py:52-71` is the closest in spirit — `test_no_session_leak.py` is essentially that script lifted into pytest with a real HTTP path. |
| `app/core/services.py` | NEW module — no existing `app/core/*.py` uses `@lru_cache(maxsize=1)`. The closest analog (`rate_limiter.py:limiter = Limiter(...)`) is a bare module-level singleton; Phase 19 prefers `@lru_cache` for lazy-init + test cache_clear handle. This file establishes a new project pattern — RESEARCH.md §Q3 owns the rationale. |

---

## Metadata

**Analog search scope:**
- `app/api/` (controllers + dependencies)
- `app/core/` (middleware, container, services, rate_limiter)
- `app/services/` (worker + auth services)
- `app/infrastructure/database/` (connection patterns)
- `tests/integration/` (fixture patterns)
- `tests/fixtures/` (test_container, database)
- `scripts/` (verify_session_leak_fix.py reproducer)

**Files scanned:** ~30 (dependencies.py 421 lines; dual_auth.py 322; csrf_middleware.py 70; container.py 189; main.py 337; websocket_api.py 158; ws_ticket_routes.py 100; whisperx_wrapper service partial; account_routes 121; key_routes partial; billing_routes partial; auth_routes partial; rate_limiter 98; connection.py 91; conftest.py 71; test_account_routes partial; test_phase11_di_smoke 86; test_argon2_benchmark 39; test_per_user_scoping partial; _phase16_helpers partial; verify_session_leak_fix 141; DEVIATIONS.md 67; 19-CONTEXT.md 352; 19-RESEARCH.md 1193).

**Pattern extraction date:** 2026-05-02

---

## PATTERN MAPPING COMPLETE

**Phase:** 19 — Auth + DI Structural Refactor
**Files classified:** 27 (3 NEW, 17 MODIFIED, 7 DELETED)
**Analogs found:** 25 / 27

### Coverage
- Files with exact analog: 18
- Files with role-match analog: 7
- Files with no analog: 2 (services.py — new project pattern; test_no_session_leak.py — combines two analogs)

### Key Patterns Identified
1. **`Depends` chain off `get_db`** — single Session per request, FastAPI dep cache shares it across all sub-deps. Replaces 16 `_container.X()` callsites in `dependencies.py`. (Pattern A)
2. **`with SessionLocal() as db:` block** — non-Depends scope (BackgroundTask, WS handler). Context manager `__exit__` closes — zero manual `.close()`. (Pattern B)
3. **`@lru_cache(maxsize=1)` factories** for stateless services in NEW `app/core/services.py`. Lazy init; test override via `app.dependency_overrides`; cache_clear handle for teardown. (Pattern C)
4. **Subtype-first exception tuples** preserved verbatim from `dual_auth.py` (`_BEARER_FAILURES`, `_COOKIE_DECODE_FAILURES`, `_COOKIE_REFRESH_FAILURES`). (Pattern D)
5. **Flat early-return guards** — verifier grep `^\s+if .*\bif\b` = 0 across `dependencies.py`, `main.py`, `services.py`. (Pattern E)
6. **Cookie attrs byte-identical** — `_set_cookie` block from `dual_auth.py:310-321` lifted verbatim into `_resolve_cookie`. Sliding refresh works because `response.set_cookie` runs BEFORE the dep returns (RESEARCH Pitfall 1). (Pattern F)

### File Created
`C:\laragon\www\whisperx\.planning\phases\19-auth-di-refactor\19-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference per-file analog patterns in T-19-01 through T-19-16 PLAN.md files. Each task already has a concrete code excerpt to copy from — no abstract guidance.
