# Phase 19: Auth + DI Structural Refactor — Research

**Researched:** 2026-05-02
**Domain:** FastAPI native `Depends` + SQLAlchemy 2.x sync `Session` lifecycle; module-level singletons; legacy middleware removal.
**Confidence:** HIGH (all locked decisions verified against official FastAPI docs + codebase grep + repro script)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D1.** Drop `dependency_injector` library entirely. Replace with module-level singletons in NEW `app/core/services.py` (`password_service`, `csrf_service`, `token_service`, `ws_ticket_service`, `WhisperX*` ML services). `Session`-bound services build inside `Depends` chain. `app/core/container.py` DELETED end-of-phase. `app/main.py` `Container()` instantiation + `dependencies.set_container(container)` calls deleted.
- **D2.** Move auth to `Depends`. Kill `DualAuthMiddleware` + `BearerAuthMiddleware`. New `authenticated_user(request, response, db=Depends(get_db))` dep handles bearer-wins-over-cookie + sliding cookie refresh + `WWW-Authenticate: Bearer realm="whisperx"` header on 401. Public routes opt-out by simply not including the dep — `PUBLIC_ALLOWLIST` deleted. Sliding-refresh routes that return their own `Response` (login/logout) skip the slide.
- **D3.** Kill `AUTH_V2_ENABLED` flag. V2 is THE auth path. Remove flag, `is_auth_v2_enabled()` helper, both branches in `app/main.py:198-208`, prod fail-loud guard at `app/main.py:257-262`, `BearerAuthMiddleware` legacy fallback.
- **D4.** Convert `CsrfMiddleware` to `Depends(csrf_protected)`. Composes with `authenticated_user`. Apply via `dependencies=[Depends(csrf_protected)]` on routers. `CsrfMiddleware` class deleted.
- **D5.** Bearer JOIN optimization OUT OF SCOPE (Phase 20). Preserve existing two-query bearer path verbatim.
- **D6.** Keep `scripts/verify_session_leak_fix.py` for one release cycle. Add `tests/integration/test_no_session_leak.py` as CI gate.

### Claude's Discretion

- Q1 — sync vs async `get_db` (research recommends sync).
- Q2 — `authenticated_user_optional` vs sentinel (research recommends two-dep pattern).
- Q3 — module-level globals vs `@lru_cache(maxsize=1)` factories (research recommends `@lru_cache`).

### Deferred Ideas (OUT OF SCOPE)

- Frontend changes — backend-only refactor.
- DB schema changes / migrations.
- Bearer JOIN perf optimization (Phase 20).
- New endpoints.
- Switching ORM/DB/web framework.
- Phase 13 documentation rewrite.
- Removing `slowapi` / replacing rate-limit machinery.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REFACTOR-01 | Zero `_container.` callsites | Mechanical replacement; section 1 (`get_db` chain) + section 4 (singletons) cover every callsite. Verifier grep gate locked at `grep -rn '_container\.' app/` = 0. |
| REFACTOR-02 | Zero manual `session.close()` outside `get_db` | FastAPI yield/finally semantics (section 1) collapse N close-calls into ONE inside `get_db`. Background task uses `with SessionLocal() as db:` (section 5) — the `__exit__` does the close, no explicit `.close()`. WS uses same context-manager pattern (section 6). Verifier grep: exactly 1 `session.close()` in `get_db`, 0 elsewhere in `app/`. |
| REFACTOR-03 | Single auth path via `Depends` | `authenticated_user` dep (section 2) — bearer-wins-over-cookie, sliding refresh, single 401 shape. Routes opt in via `Depends(authenticated_user)`. WS uses ticket flow (no Depends) but consumes same `authenticated_user` for the issuing HTTP route. |
| REFACTOR-04 | `AUTH_V2_ENABLED` + `BearerAuthMiddleware` deleted | Section 10 (deletion order). After all routes use `Depends`, both middleware classes + flag delete in T-19-10. |
| REFACTOR-05 | `dependency_injector` dependency removed | After T-19-12 deletes `container.py`, `pyproject.toml` line 31 `"dependency-injector>=4.41.0"` removed; `uv lock` regenerated. Verifier: `grep -rn 'dependency_injector' app/ tests/` = 0. |
| REFACTOR-06 | No test count regression | Section 7 + 8 — `app.dependency_overrides[get_db]` migration; `tests/baseline_phase19.txt` snapshot at T-19-01 vs end-of-phase `pytest --collect-only` diff. |
| REFACTOR-07 | `Set-Cookie` attributes byte-identical | Section 5 (sliding refresh) preserves max_age/httponly/secure/samesite/path/domain verbatim. Playwright e2e gate (`bun run test:e2e`) compares wire bytes. |
</phase_requirements>

## Summary

The current architecture is the textbook anti-pattern for FastAPI: a `dependency_injector` `Container` whose `Factory` providers create per-request services with embedded `SessionLocal()` calls, accessed via a global `_container` reference from BOTH `Depends` providers AND middleware/WS/background contexts. The result is 16 `_container.X()` callsites in `dependencies.py` plus 11 more in non-Depends code paths, each requiring a manual `try/finally service.repository.session.close()` pattern that has now been added in two consecutive bug-fix commits (`0f7bb09` `Factory-DI provider stall` → `61c9d61` `middleware/background container.X() calls`).

The fix structure is well-known and idiomatic FastAPI 2026: ONE `get_db` generator with `yield/finally session.close()`, repos and services chained off it via `Depends`, stateless services as `@lru_cache(maxsize=1)` factories, auth as a `Depends(authenticated_user)` (not a middleware), CSRF as a `Depends(csrf_protected)` composed off auth. WS and background contexts (where `Depends` is unavailable) use explicit `with SessionLocal() as db:` blocks — the context manager's `__exit__` does the close; no manual `.close()` boilerplate.

Sliding-cookie refresh works inside a `Depends` because FastAPI runs the dep BEFORE calling the route; the route receives the `response: Response` and FastAPI serializes its headers AFTER the route returns but BEFORE the dep's `finally` runs. Cookies set in the dep's pre-yield body therefore make it onto the wire — verified against the official FastAPI yield-dependency lifecycle diagram.

**Primary recommendation:** Execute the planner-suggested 16-step order verbatim. Each `T-19-NN` is one atomic commit; the suite stays green between commits because new helpers coexist with old `_container.X()` callsites until the very last sweep. The deletion order matters: `container.py` is deleted LAST (T-19-12) — deleting it first would break every callsite simultaneously.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP request session lifecycle | API/Backend (FastAPI Depends) | — | `get_db` yield/finally is FastAPI-native; one Session per request, closed automatically. |
| Auth resolution (bearer + cookie) | API/Backend (Depends) | — | Currently a middleware; refactor moves to a per-route Depends so opt-in/out is per-route, no allowlist regression risk. |
| CSRF check | API/Backend (Depends) | — | Currently a middleware; refactor moves to `dependencies=[Depends(csrf_protected)]` — composable with `Depends(authenticated_user)`. |
| Stateless service instances | Module (Python) | API/Backend (Depends wrapper for tests) | `password_service`, `csrf_service`, `token_service`, `ws_ticket_service`, ML services — no per-request state, `@lru_cache(maxsize=1)` factory. |
| WS connection auth | API/Backend (ticket flow + manual `with SessionLocal()`) | — | WS is not dispatched via FastAPI HTTP `Depends`; ticket-issuing HTTP route uses `Depends(authenticated_user)`; WS handler validates ticket then opens its own short-lived session via `with SessionLocal() as db:`. |
| Background-task DB access | Service (worker) | — | `BackgroundTask` runs after response sent; must NOT inherit request session. Pattern: explicit `with SessionLocal() as db:` for the worker's own scope. |
| Frontend HTTP contract | Browser | API/Backend (read-only) | Backend-only refactor — frontend untouched; Playwright e2e is the verification surface. |

## Q1-Q3 Concrete Answers

### Q1. Should `get_db` be sync or async?

**Recommendation: STAY SYNC.**

**Evidence:**

1. **Codebase reality:** `app/infrastructure/database/connection.py:19` uses `from sqlalchemy.orm import Session, sessionmaker` (sync). `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)` is the sync flavor. Engine is `create_engine(DB_URL, connect_args={"check_same_thread": False})` (sync). Switching to async requires `create_async_engine`, `AsyncSession`, every repo method `async def`, every route `async def db.execute(stmt)` instead of `db.query(M).filter(...).first()` — that's a Phase 20+ migration, not a Phase 19 concern. [VERIFIED: codebase grep + Read of `app/infrastructure/database/connection.py`]
2. **FastAPI tutorial canonical pattern is sync:** the SQL Databases tutorial uses `def get_session()` with `with Session(engine) as session: yield session` — sync def, sync context manager. [CITED: https://fastapi.tiangolo.com/tutorial/sql-databases/]
3. **Phase 19 perf target is "no leak", not "throughput":** the verification gate is "50 sequential requests <100ms each" — easily met by sync SQLAlchemy on SQLite (single-writer file). Async would buy nothing because SQLite is GIL-bound on writes. [VERIFIED: 19-CONTEXT.md verification gate 8]
4. **Known async pitfall (deadlock):** FastAPI/SQLAlchemy GitHub Discussion #6628 documents thread-pool-deadlock when sync `db.execute()` blocks anyio worker threads while `finally` cleanup queues behind it. Resolved in FastAPI 0.82.0+ (whisperX uses 0.128.0, safe), but it's a known landmine. Sync def + sync context manager keeps cleanup on the same coroutine. [CITED: https://github.com/fastapi/fastapi/discussions/6628]

**Locked pattern:**

```python
# app/api/dependencies.py — new
from collections.abc import Generator
from sqlalchemy.orm import Session
from app.infrastructure.database.connection import SessionLocal

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

When does Phase 20+ pay off in async? When the codebase adds (a) external HTTP calls inside repos (`httpx.AsyncClient`), (b) Postgres backend (`asyncpg` driver — true concurrency), or (c) WebSocket fan-out backed by DB queries (current WS just emits in-memory progress). None of these apply to v1.2.

### Q2. `authenticated_user_optional` vs sentinel?

**Recommendation: TWO SEPARATE DEPS — `authenticated_user` and `authenticated_user_optional`.**

**Evidence:**

1. **Idiomatic FastAPI:** `HTTPBearer(auto_error=True)` raises 401 by default; `HTTPBearer(auto_error=False)` returns `None`. Two distinct security schemes — separate dependencies. The codebase already mirrors this pattern in spirit at `app/api/dependencies.py:203-217` (`get_authenticated_user`) — there's no current optional variant because the Phase-13 surface has zero anonymous-allowed authed routes. [CITED: FastAPI Security Tools — https://fastapi.tiangolo.com/reference/security/]
2. **Type narrowing at call sites:** Sentinel returns `User | AnonymousSentinel` which forces `if isinstance(user, AnonymousSentinel)` checks at every call site (nested-if violation per CLAUDE.md). Two deps return `User` vs `User | None` — caller picks the dep that gives the right type. [VERIFIED: CLAUDE.md "no nested-if spaghetti"]
3. **OpenAPI surface:** The two-dep pattern produces correct OpenAPI security schemes per route — required vs optional. A sentinel hides this from the schema generator. [CITED: FastAPI Security Tools]

**Locked pattern:**

```python
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
    return _try_resolve(request, response, db)  # None on any failure
```

`_try_resolve` is the shared private helper — bearer-wins, then cookie, then None. DRY. The `User | None` return type is exact; no sentinel arithmetic at call sites.

**Note:** Phase 19 scope has ZERO routes that need `authenticated_user_optional` today. Add it as a placeholder (with one unit test asserting 200 + None for no-auth, 200 + user for valid cookie) so future routes have a ready handle without re-debating the pattern.

### Q3. Module-level globals vs `@lru_cache(maxsize=1)` for `app/core/services.py`?

**Recommendation: `@lru_cache(maxsize=1)` factory functions.**

**Evidence:**

1. **FastAPI tutorial canonical pattern:** the `Settings` tutorial uses exactly this pattern (`@lru_cache def get_settings(): return Settings()`) and explicitly recommends it for "expensive operations done once". Same applies to `TokenService` (constructs JWT secret unwrap), `WhisperXTranscriptionService` (loads ML model — expensive), etc. [CITED: https://fastapi.tiangolo.com/advanced/settings/]
2. **Test override is identical to module-level globals + cleaner:** `app.dependency_overrides[get_password_service] = lambda: FakePasswordService()` works regardless of whether the dep is `@lru_cache` or `return _GLOBAL`. The `@lru_cache` form has the advantage that the cache itself can be cleared via `get_password_service.cache_clear()` in test teardown — module-level globals have no such handle. [CITED: https://fastapi.tiangolo.com/tutorial/testing/]
3. **Lazy init:** `@lru_cache` defers construction until first call. Module-level globals construct at import time. ML services in particular (TranscriptionService, etc.) load PyTorch models on construction — deferring to first use means CLI commands and migrations don't pay that cost. [VERIFIED: `app/infrastructure/ml/__init__.py` exports load WhisperX models in `__init__`]
4. **Type sig of dep-override is the same:** `app.dependency_overrides[get_csrf_service] = lambda: stub` — clean, consistent with `get_db` override pattern. Module-level `csrf_service = CsrfService()` would require monkeypatching `app.core.services.csrf_service` which collides with import-time imports.

**Locked pattern:**

```python
# app/core/services.py — NEW FILE

from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.ml import (
    WhisperXAlignmentService,
    WhisperXDiarizationService,
    WhisperXSpeakerAssignmentService,
    WhisperXTranscriptionService,
)
from app.services.auth.csrf_service import CsrfService
from app.services.auth.password_service import PasswordService
from app.services.auth.token_service import TokenService
from app.services.file_service import FileService
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


@lru_cache(maxsize=1)
def get_file_service() -> FileService:
    return FileService()


# ML services — lazy because model loading is heavy
@lru_cache(maxsize=1)
def get_transcription_service() -> WhisperXTranscriptionService:
    return WhisperXTranscriptionService()


@lru_cache(maxsize=1)
def get_diarization_service() -> WhisperXDiarizationService:
    return WhisperXDiarizationService(
        hf_token=get_settings().whisper.HF_TOKEN,
    )


@lru_cache(maxsize=1)
def get_alignment_service() -> WhisperXAlignmentService:
    return WhisperXAlignmentService()


@lru_cache(maxsize=1)
def get_speaker_assignment_service() -> WhisperXSpeakerAssignmentService:
    return WhisperXSpeakerAssignmentService()
```

**Critical contract:** `WsTicketService` Singleton lifecycle MUST persist across requests — the in-memory ticket dict is shared state. `@lru_cache(maxsize=1)` enforces single-instance just like the current `providers.Singleton(WsTicketService)`. A Factory would silently break the ticket store. [VERIFIED: `app/services/ws_ticket_service.py:53-64` — instance state is `self._tickets: dict` + `self._lock: threading.Lock`]

## Standard Stack

### Core (already pinned in pyproject.toml — DO NOT CHANGE)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.128.0 | Web framework | Already pinned; 0.82.0+ resolves the anyio thread-pool deadlock — safe for sync `Depends` chains [CITED: https://github.com/fastapi/fastapi/discussions/6628] |
| SQLAlchemy | 2.x sync | ORM | Already in use; sync `Session` + `sessionmaker(SessionLocal)` |
| starlette | (FastAPI dep) | ASGI primitives | `BaseHTTPMiddleware` only used by `DualAuthMiddleware` + `CsrfMiddleware` — both deleted by Phase 19 |
| pyjwt | >=2.8.0 | JWT codec | unchanged |
| argon2-cffi | >=23.1.0 | Password hashing | unchanged |
| slowapi | >=0.1.9 | Rate limiting | unchanged — `@limiter.limit("3/hour")` decorators continue to work post-refactor |

### Removed

| Library | Action | Why |
|---------|--------|-----|
| dependency-injector | DELETE from `pyproject.toml` line 31 | D1 — replaced by `Depends` chain + `@lru_cache` |

**Installation:** No new packages. Just remove `dependency-injector` line from `[project] dependencies` and re-lock with `uv lock`.

**Version verification:**

```bash
.venv/Scripts/python.exe -c "import fastapi; print(fastapi.__version__)"  # 0.128.0
.venv/Scripts/python.exe -c "import sqlalchemy; print(sqlalchemy.__version__)"  # 2.x
```

[VERIFIED: `pyproject.toml` lines 30-58 read 2026-05-02]

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────┐
│  HTTP Request       │
│  (cookie | bearer)  │
└──────────┬──────────┘
           │
           ▼
   ┌────────────────────┐
   │ CORSMiddleware     │  (only middleware left after Phase 19)
   └──────────┬─────────┘
              │
              ▼
   ┌──────────────────────────┐
   │ Route                    │
   │   Depends(get_db) ───────┼──> SessionLocal() per request
   │   Depends(authenticated  │
   │     _user) ──────────────┼──> bearer-wins | cookie+slide | 401
   │   Depends(csrf_protected)│  (only on cookie-auth state-mutating)
   │   Depends(get_*_service) │  (per-request services bound to db)
   │   Depends(get_password_  │  (@lru_cache singletons)
   │     service)             │
   └──────────┬───────────────┘
              │
              ▼ route body
              │
              ▼
        Response (cookies set on response: Response param)
              │
              ▼ FastAPI serializes Response headers + body
              │
              ▼
        Dependency `finally` blocks run (db.close()) — AFTER wire
              │
              ▼
        Connection returned to engine pool

────────────────────────────────────────────────────────────────────
WebSocket scope (no Depends):
   /ws/tasks/{id}?ticket=...
        │
        ▼
   five flat guards (incl. WsTicketService.consume)
        │
        ▼
   with SessionLocal() as db:    ← short-lived; closes on context exit
       ...defence-in-depth task lookup, then bridge to connection_manager
────────────────────────────────────────────────────────────────────
BackgroundTask scope (no Depends, no Request):
   process_audio_common(...)
        │
        ▼
   with SessionLocal() as db:    ← worker's own session; closes on exit
       repo = SQLAlchemyTaskRepository(db)
       free_tier_gate = FreeTierGate(...)  # constructed inline, db-bound
       ...
       (success | failure) finally: release_concurrency(user)
   (context exit closes db)
```

### Recommended Project Structure (post-Phase-19)

```
app/
├── api/
│   ├── dependencies.py        REWRITTEN — get_db, repo deps, authenticated_user, csrf_protected
│   ├── auth_routes.py         re-wired
│   ├── account_routes.py      re-wired
│   ├── key_routes.py          re-wired
│   ├── billing_routes.py      re-wired
│   ├── task_api.py            re-wired
│   ├── ws_ticket_routes.py    re-wired (singleton import + Depends)
│   └── websocket_api.py       rewritten — `with SessionLocal()` block
├── core/
│   ├── auth.py                DELETED (BearerAuthMiddleware)
│   ├── container.py           DELETED
│   ├── csrf_middleware.py     DELETED
│   ├── dual_auth.py           DELETED
│   ├── feature_flags.py       (only is_auth_v2_enabled removed; rest stays)
│   └── services.py            NEW — @lru_cache singletons
├── services/
│   └── whisperx_wrapper_service.py   rewritten — `with SessionLocal()` worker block
└── main.py                     trimmed — no Container(), no AUTH_V2 branches, no prod guard
```

### Pattern 1: `get_db` (the canonical FastAPI/SQLAlchemy 2.x sync pattern)

**What:** ONE generator dep that yields a `Session`. Every other dep that needs a DB chains off it via `Depends(get_db)`.
**When to use:** Every HTTP route that touches the DB. Period.
**Example:**
```python
# app/api/dependencies.py — Phase 19 final

from collections.abc import Generator
from sqlalchemy.orm import Session
from app.infrastructure.database.connection import SessionLocal

def get_db() -> Generator[Session, None, None]:
    """ONE place that owns Session.close(). The yield/finally pattern is
    FastAPI-native: finally runs AFTER the response is on the wire, so
    cookies set inside dependents still serialize.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```
**Source:** [CITED: https://fastapi.tiangolo.com/tutorial/sql-databases/]

### Pattern 2: Repository deps chained off `get_db`

```python
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)

def get_user_repository(db: Session = Depends(get_db)) -> IUserRepository:
    return SQLAlchemyUserRepository(db)

def get_api_key_repository(db: Session = Depends(get_db)) -> IApiKeyRepository:
    return SQLAlchemyApiKeyRepository(db)

def get_task_repository(db: Session = Depends(get_db)) -> ITaskRepository:
    return SQLAlchemyTaskRepository(db)

def get_rate_limit_repository(db: Session = Depends(get_db)) -> IRateLimitRepository:
    return SQLAlchemyRateLimitRepository(db)
```

**Single resolution per request:** FastAPI caches `Depends(get_db)` for the duration of one request — every dep that depends on `get_db` shares ONE Session. Sliding-cookie refresh, the route, and the CSRF check all see the same `db`. [CITED: FastAPI Dependencies tutorial — caching is on by default]

### Pattern 3: Service deps (per-request, db-bound)

```python
def get_auth_service(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(
        user_repository=user_repo,
        password_service=get_password_service(),  # @lru_cache singleton — direct call
        token_service=get_token_service(),
    )

def get_key_service(
    api_key_repo: IApiKeyRepository = Depends(get_api_key_repository),
) -> KeyService:
    return KeyService(repository=api_key_repo)

def get_rate_limit_service(
    rate_repo: IRateLimitRepository = Depends(get_rate_limit_repository),
) -> RateLimitService:
    return RateLimitService(repository=rate_repo)

def get_free_tier_gate(
    rate_service: RateLimitService = Depends(get_rate_limit_service),
) -> FreeTierGate:
    return FreeTierGate(rate_limit_service=rate_service)

def get_usage_event_writer(db: Session = Depends(get_db)) -> UsageEventWriter:
    return UsageEventWriter(session=db)
```

Notice: ZERO `try/finally session.close()` boilerplate. The `get_db` finally handles all of them via FastAPI's dep cache (one Session per request, closed once at request end).

### Pattern 4: `authenticated_user` (replacing `DualAuthMiddleware`)

```python
# app/api/dependencies.py — Phase 19

from datetime import datetime, timezone
from fastapi import HTTPException, Request, Response
from app.core import jwt_codec
from app.core.config import get_settings
from app.core.exceptions import (
    InvalidApiKeyFormatError, InvalidApiKeyHashError,
    JwtExpiredError, JwtAlgorithmError, JwtTamperedError,
)
from app.domain.entities.user import User

SESSION_COOKIE = "session"
BEARER_PREFIX = "Bearer "
_BEARER_FAILURES = (InvalidApiKeyFormatError, InvalidApiKeyHashError)
_COOKIE_DECODE_FAILURES = (JwtExpiredError, JwtAlgorithmError, JwtTamperedError, KeyError, ValueError)


def _resolve_bearer(plaintext: str, db: Session) -> User | None:
    """Same two-query path as Phase 13 verbatim. Phase 20 will collapse to one JOIN."""
    key_service = KeyService(repository=SQLAlchemyApiKeyRepository(db))
    try:
        api_key = key_service.verify_plaintext(plaintext)
    except _BEARER_FAILURES:
        return None
    user = SQLAlchemyUserRepository(db).get_by_id(api_key.user_id)
    return user


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
        _payload, refreshed = get_token_service().verify_and_refresh(
            token, user.token_version,
        )
    except (JwtExpiredError, JwtAlgorithmError, JwtTamperedError):
        return None
    # Sliding refresh — cookie attrs locked in app/api/_cookie_helpers.py.
    settings = get_settings()
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
    request: Request, response: Response, db: Session,
) -> User | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith(BEARER_PREFIX):  # bearer wins
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

**Why this works for sliding refresh** (the non-obvious lifecycle ordering):

1. FastAPI resolves `Depends(authenticated_user)` BEFORE calling the route.
2. `authenticated_user` calls `_resolve_cookie(...)` which sets `response.set_cookie(...)` on the request-scoped `Response` object.
3. The route runs. If the route returns a Pydantic model / dict, FastAPI serializes the model and ATTACHES the headers from the injected `response: Response` to the final wire response.
4. FastAPI sends the response (status, headers including Set-Cookie, body) on the wire.
5. ONLY THEN does `get_db`'s `finally db.close()` run.

So `response.set_cookie` BEFORE yield (here, "before yield" = "in the dep body before the dep returns") makes it onto the wire. Set-cookie AFTER yield (in a `finally`) does NOT — that's documented in the FastAPI yield-deps tutorial. [CITED: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/]

**Sliding-skip policy:** `/auth/login`, `/auth/logout`, `/auth/logout-all` return their own `Response` object (verified — `app/api/auth_routes.py:184-214`). Per the FastAPI tutorial, FastAPI ignores the injected `Response` when the route returns an explicit `Response` — so even though the dep set a cookie on the injected one, that cookie does NOT make it onto the explicitly-returned wire response. The route's own `Set-Cookie: session=<NEW>` headers (login) or `Set-Cookie: session=` deletions (logout) are what users see. **This is CORRECT behavior** — login/logout don't include `Depends(authenticated_user)` anyway, so the slide path never runs for them. (Login is unauth-by-design; logout is auth-cookie clearing — the slide would re-issue what we're trying to clear.)

### Pattern 5: `csrf_protected` (replacing `CsrfMiddleware`)

```python
def csrf_protected(
    request: Request,
    user: User = Depends(authenticated_user),  # auth runs first (DRT)
) -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return  # GET/HEAD/OPTIONS skip
    auth = request.headers.get("authorization", "")
    if auth.startswith(BEARER_PREFIX):
        return  # bearer skips CSRF (external API clients)
    cookie = request.cookies.get("csrf_token", "")
    header = request.headers.get("x-csrf-token", "")
    if not header:
        raise HTTPException(403, "CSRF token missing")
    if not get_csrf_service().verify(cookie, header):
        raise HTTPException(403, "CSRF token mismatch")
```

**Wired on routers:**
```python
# app/api/__init__.py or per-router
key_router = APIRouter(
    prefix="/api/keys", tags=["API Keys"],
    dependencies=[Depends(csrf_protected)],
)
account_router = APIRouter(
    prefix="/api/account", tags=["Account"],
    dependencies=[Depends(csrf_protected)],
)
billing_router = APIRouter(
    prefix="/billing", tags=["Billing"],
    dependencies=[Depends(csrf_protected)],
)
# auth_router stays bare — login/register/logout don't need csrf_protected
#   (no auth cookie present yet for login/register; logout uses bearer-like
#    semantics in that the csrf check would block legitimate logout-all)
```

**`/auth/logout-all` decision:** It IS state-mutating cookie-auth. Existing test (`test_auth_routes::test_logout_all_*` in tests/integration) expects 403 on missing `X-CSRF-Token`. Add `Depends(csrf_protected)` to `/auth/logout-all` route directly (NOT to the auth router blanket) — preserves Phase 13 behavior verbatim. [VERIFIED: 19-CONTEXT.md verification gate 14 + STATE.md `[15-02]` entry — `/auth/logout-all` 403 on missing CSRF]

### Anti-Patterns to Avoid

- **Calling `_container.X()` ANYWHERE.** Verifier grep gate: 0 hits. The whole point of Phase 19.
- **Manual `try/finally service.repository.session.close()` in any provider.** ONE close inside `get_db` — that's it.
- **Setting a cookie in a `Depends` `finally` block.** Cookies set after `yield` do NOT make it onto the wire. [CITED: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/]
- **Reusing a request-scoped Session in a `BackgroundTask`.** The session closes when the request finishes; the BackgroundTask runs after. Pass user_ids/task_ids only — open a fresh `with SessionLocal() as db:` inside the task. [CITED: GitHub Discussion #6628]
- **Re-introducing a middleware for auth.** The whole point is per-route opt-in via `Depends`. Middlewares are global and tied to path-allowlist gymnastics.
- **Using `app.dependency_overrides[get_db] = lambda: session` WITHOUT cleanup.** Tests must `app.dependency_overrides.clear()` in fixture teardown — leaks bleed across test files. [CITED: https://fastapi.tiangolo.com/tutorial/testing/]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-request DB session | Custom session-pool wrapper | `Depends(get_db)` with yield/finally | FastAPI's dep cache shares the Session across all sub-deps in one request automatically; lifecycle is guaranteed correct. |
| Bearer/cookie auth | Custom Starlette `BaseHTTPMiddleware` | `Depends(authenticated_user)` | Middleware-based auth couples to global path-allowlist + can't access request-scoped DB session without container reach-in (the very anti-pattern Phase 19 deletes). |
| CSRF enforcement | Custom `BaseHTTPMiddleware` | `Depends(csrf_protected)` on routers | Middleware can't compose with auth dep (can't read request-scoped User without re-resolving). Dep composes naturally: `Depends(csrf_protected) -> Depends(authenticated_user) -> Depends(get_db)`. |
| Service singletons | `dependency_injector.providers.Singleton` | `@lru_cache(maxsize=1)` factories in `app/core/services.py` | Stdlib only; testable via `app.dependency_overrides` AND `cache_clear()`; lazy init; no extra dep on `dependency-injector` library. |
| Background-task DB access | Reach into `_container.X()` to get a Session | Explicit `with SessionLocal() as db:` block | Background scope has no Request, no Depends. Context manager is the FastAPI/SQLAlchemy-native way to scope a Session to a worker. [CITED: GitHub Discussion #6628] |
| WS auth | Re-use `Depends(authenticated_user)` in WS handler | Existing ticket flow + `with SessionLocal()` for the WS handler's own short-lived DB needs | FastAPI `Depends` doesn't apply to WS scope. Ticket-issuing HTTP route does use `Depends(authenticated_user)`. |
| Replacement DI library | Bring in `python-inject` / `wireup` / similar | FastAPI native `Depends` | The codebase has 0 `@inject` decorators and 0 `Provide[...]` parameters today — there's no DI graph to preserve. Adding another library replaces one anti-pattern with another. |

**Key insight:** `dependency-injector`'s value lies in deep DI graphs with `@inject` + `Provide[...]` patterns. The codebase uses NONE of that — it just calls `_container.X()` from within global functions. Removing the library is a pure simplification, not a re-architecture.

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — DB schema unchanged. `users.token_version` semantics preserved verbatim. SQLite file untouched. | None |
| Live service config | None — slowapi limiter, CORS allowlist, FRONTEND_URL all unchanged. | None |
| OS-registered state | None — pm2/systemd/Task Scheduler entries (if any in deploy) call `uvicorn app.main:app` which still works post-refactor. | None |
| Secrets / env vars | `AUTH__V2_ENABLED` env var becomes dead — code reads it at boot, but the branches it gates are deleted. The variable in `.env` / deploy is harmless once the code stops checking. **Action:** add a `.env.example` cleanup line in T-19-15 dead-code sweep noting `AUTH__V2_ENABLED` is no longer read. | Cleanup `.env.example` only — actual deployment .env unchanged on disk; just dead. |
| Build artifacts / installed packages | `dependency-injector` package still in `.venv/Lib/site-packages/` after `pyproject.toml` line removed. **Action:** `uv lock && uv sync` OR `.venv/Scripts/pip uninstall dependency-injector -y` after T-19-12 lands. | `uv sync` rebuilds env without the package. |

**The canonical question:** *After every file in the repo is updated, what runtime systems still have the old structure cached, stored, or registered?*

Answer: only the `.venv` package itself + a dead env var. Both are recoverable in seconds. **No data migration. No service-config update. No OS state.** Phase 19 is structurally pure — the wire contract and DB schema are byte-identical pre/post.

## Common Pitfalls

### Pitfall 1: Setting `Set-Cookie` from a `Depends` `finally` block

**What goes wrong:** Cookies set in the `finally` block of a yield-dep don't make it onto the wire. The response is already serialized.

**Why it happens:** FastAPI's documented lifecycle: `route returns → response built → response sent → dep finally runs`. [CITED: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/]

**How to avoid:** Set cookies BEFORE `yield` (or in deps that don't yield, anywhere before `return`). The sliding-refresh pattern in `_resolve_cookie` works because `response.set_cookie(...)` is called inside the dep body BEFORE returning — `authenticated_user` does NOT use yield/finally for the response mutation; only `get_db` uses yield/finally for the Session lifecycle.

**Warning signs:** "Sliding cookie test passes locally but Playwright e2e shows the second request not finding the cookie." Means the cookie was set after the wire flush.

### Pitfall 2: Reusing request-scoped Session in `BackgroundTask`

**What goes wrong:** `BackgroundTask(my_func, db=db)` where `db` came from `Depends(get_db)`. The request finishes, `get_db` finally closes the session, then the BackgroundTask runs and operates on a closed Session — `DetachedInstanceError` or `InvalidRequestError`.

**Why it happens:** `BackgroundTask` is FastAPI's "after-response" hook. The dep's `finally` always wins the race.

**How to avoid:** Pass scalar arguments (user_id, task_uuid) only. Open a fresh `with SessionLocal() as db:` inside the worker:

```python
def process_audio_common(...):
    with SessionLocal() as db:
        repository = SQLAlchemyTaskRepository(db)
        # ...all the work...
    # context exit closes db automatically — NO manual close()
```

**Warning signs:** Errors with `Instance is not bound to a Session` after the response was already 200. The current implementation in `whisperx_wrapper_service.py` opens its OWN `session = SessionLocal()` and closes it manually in finally — Phase 19 converts that to `with SessionLocal() as db:` (REFACTOR-02 collapses the manual close).

[CITED: https://github.com/fastapi/fastapi/discussions/6628]

### Pitfall 3: Public-allowlist regression when an auth dep is added globally

**What goes wrong:** Adding `dependencies=[Depends(authenticated_user)]` to the FastAPI app instance (instead of per-router) breaks `/health`, `/auth/login`, `/auth/register`, `/billing/webhook`, `/static/*`.

**Why it happens:** `app.dependencies=[...]` applies to EVERY route. Public routes need NO dep — that's the whole point of opt-in.

**How to avoid:** NEVER add auth deps at app level. Per-router OR per-route only. Migration order in T-19-06..07 proves this — first migrate `/api/account/me`, then sweep router-by-router. `app/main.py` `app = FastAPI(...)` constructor stays clean (no `dependencies=[...]`).

**Warning signs:** `/auth/login` returns 401 — means an auth dep slipped onto a public-by-design route. The existing `PUBLIC_ALLOWLIST` becomes meaningless once routes opt-in individually; deleting the list (T-19-15) is correct only AFTER every router is verified.

### Pitfall 4: WebSocket trying to use `Depends(authenticated_user)`

**What goes wrong:** `@websocket_router.websocket("/...")` route declares `user: User = Depends(authenticated_user)` — TypeError or silent skip.

**Why it happens:** FastAPI HTTP `Depends` does not propagate to WS scope. WS dispatch uses Starlette's `WebSocketRoute`, not the HTTP dep system. (You CAN use FastAPI `Depends` in WS routes, but not the kind that depend on `Request` / HTTP headers — only those that depend on `WebSocket`.) The `Depends(get_db)` pattern actually works in WS scope, but `authenticated_user` won't because it depends on `Request` (HTTP-only).

**How to avoid:** Keep the existing ticket flow. The HTTP route `POST /api/ws/ticket` uses `Depends(authenticated_user)`; the WS handler validates the ticket without any auth Depends. WS handler opens its own `with SessionLocal() as db:` block for any DB lookup it needs.

**Warning signs:** `RuntimeError: 'Request' object is not available` raised at WS connection time.

### Pitfall 5: `slowapi` `@limiter.limit` decorator vs missing `request: Request` parameter

**What goes wrong:** `@limiter.limit("3/hour")` decorator on `/auth/register` requires the route to accept `request: Request` as the FIRST positional arg. After Phase 19 refactor a careless route signature change drops it.

**Why it happens:** slowapi reads `request.client.host` to compute the rate-limit key — it can't if `request` isn't passed in.

**How to avoid:** Preserve every `request: Request` parameter on rate-limited routes verbatim. `auth_routes.py:124-180` already uses `async def register(request: Request, response: Response, body: RegisterRequest, ...)` — keep this shape; only change the `Depends` chain.

**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'client'` raised inside slowapi handler.

### Pitfall 6: `app.dependency_overrides` test isolation leak

**What goes wrong:** Test A overrides `get_db`, doesn't clear it; Test B inherits the override and sees Test A's session.

**Why it happens:** `app.dependency_overrides` is a module-global dict on the FastAPI app instance. Pytest doesn't reset it between tests by default.

**How to avoid:** autouse fixture in `tests/conftest.py`:
```python
@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    from app.main import app
    app.dependency_overrides.clear()
```

Or an explicit `try/finally app.dependency_overrides.pop(get_db, None)` per test. [CITED: https://fastapi.tiangolo.com/tutorial/testing/]

**Warning signs:** Tests pass in isolation, fail when run together. Test count regression between baseline and post-refactor (REFACTOR-06 tripped).

### Pitfall 7: `@lru_cache` cross-test contamination

**What goes wrong:** Test A monkey-patches `get_token_service`'s cached return value; Test B sees the patch because the cache persists across tests.

**Why it happens:** `@lru_cache` cache lives on the function object — module-global, never resets.

**How to avoid:** Clear the cache in fixture teardown OR use `app.dependency_overrides[get_token_service] = lambda: fake` instead of monkey-patching. Override is per-test and auto-cleared by the fixture above.

```python
@pytest.fixture(autouse=True)
def _clear_lru_caches():
    yield
    from app.core import services
    services.get_password_service.cache_clear()
    services.get_csrf_service.cache_clear()
    services.get_token_service.cache_clear()
    services.get_ws_ticket_service.cache_clear()
    # ... ML services not cached-cleared in tests because they're never instantiated under unit/integration ...
```

[CITED: https://docs.python.org/3/library/functools.html#functools.lru_cache `cache_clear()`]

### Pitfall 8: Deleting `container.py` before all callsites are migrated

**What goes wrong:** `git rm app/core/container.py` before T-19-06..09 finish — every `_container.X()` callsite raises `ImportError` at module load. App refuses to start. CI red.

**Why it happens:** Deletion is total; coexistence is needed during incremental migration.

**How to avoid:** Strict 16-step order. Container stays alive (and the `_container: Container | None = None` global stays in dependencies.py) UNTIL T-19-12 — the LAST step before the no-leak regression test (T-19-13) and frontend e2e (T-19-14). Each prior step must leave EVERY caller working.

**Warning signs:** Mid-refactor commit boots but fails on first real request. Means a route was migrated to new deps but a referenced module still has `_container.X()` reach-in.

## Code Examples

### Example 1: Migration of `/api/account/me` (the T-19-06 first-route pilot)

**BEFORE (current — Phase 13):**
```python
# app/api/account_routes.py
from fastapi import APIRouter, Depends
from app.api.dependencies import get_authenticated_user, get_db_session
from app.api.schemas.account_schemas import AccountSummaryResponse
from app.domain.entities.user import User
from app.services.account_service import AccountService

account_router = APIRouter(prefix="/api/account", tags=["Account"])

@account_router.get("/me", response_model=AccountSummaryResponse)
async def get_account_summary(
    user: User = Depends(get_authenticated_user),  # reads request.state.user
    db: Session = Depends(get_db_session),
) -> AccountSummaryResponse:
    summary = AccountService(session=db).get_account_summary(int(user.id))
    return AccountSummaryResponse(**summary)
```

**AFTER (Phase 19):**
```python
# app/api/account_routes.py
from fastapi import APIRouter, Depends
from app.api.dependencies import authenticated_user, get_db
from app.api.schemas.account_schemas import AccountSummaryResponse
from app.domain.entities.user import User
from app.services.account_service import AccountService

account_router = APIRouter(prefix="/api/account", tags=["Account"])

@account_router.get("/me", response_model=AccountSummaryResponse)
async def get_account_summary(
    user: User = Depends(authenticated_user),  # full bearer/cookie/slide flow
    db: Session = Depends(get_db),  # shared with authenticated_user — same Session
) -> AccountSummaryResponse:
    summary = AccountService(session=db).get_account_summary(int(user.id))
    return AccountSummaryResponse(**summary)
```

Notice: ONE Session per request, shared between `authenticated_user` and the route. ZERO try/finally. Frontend contract identical.

### Example 2: WebSocket migration (T-19-08)

**BEFORE:**
```python
# app/api/websocket_api.py — Phase 13 + leak fix
from app.api import dependencies
# ...
ticket_service = dependencies._container.ws_ticket_service()
task_repo = dependencies._container.task_repository()
try:
    task = task_repo.get_by_id(task_id)
finally:
    task_repo.session.close()
```

**AFTER:**
```python
# app/api/websocket_api.py — Phase 19
from app.core.services import get_ws_ticket_service
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)

@websocket_router.websocket("/ws/tasks/{task_id}")
async def websocket_task_progress(
    websocket: WebSocket,
    task_id: str,
    ticket: str = Query(default=""),
) -> None:
    if not ticket:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return
    ticket_service = get_ws_ticket_service()  # @lru_cache singleton

    with SessionLocal() as db:  # short-lived; closes on context exit
        task = SQLAlchemyTaskRepository(db).get_by_id(task_id)
    # session is now closed; we have the task entity in memory

    if task is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return
    consumed_user_id = ticket_service.consume(ticket, task_id)
    if consumed_user_id is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return
    if consumed_user_id != task.user_id:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return
    # ... rest unchanged: connection_manager.connect, heartbeat loop ...
```

### Example 3: Background task migration (T-19-09)

**BEFORE (current):**
```python
# app/services/whisperx_wrapper_service.py — Phase 13 + leak fix
session = SessionLocal()
repository: ITaskRepository = SQLAlchemyTaskRepository(session)
# ... 200 lines of work ...
free_tier_gate = _container.free_tier_gate()
usage_writer = _container.usage_event_writer()
# ... try/except/finally with manual closes:
finally:
    if free_tier_gate is not None:
        free_tier_gate.rate_limit_service.repository.session.close()
    if usage_writer is not None:
        usage_writer.session.close()
    session.close()
```

**AFTER (Phase 19):**
```python
# app/services/whisperx_wrapper_service.py — Phase 19
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.services.free_tier_gate import FreeTierGate
from app.services.auth import RateLimitService
from app.services.usage_event_writer import UsageEventWriter


def process_audio_common(params, ...):
    with SessionLocal() as db:  # one session for the whole worker
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
            # ... failure handling ...
            transcription_succeeded = False

        finally:
            # W1 contract — release slot on success AND failure
            completed_task = repository.get_by_id(params.identifier)
            if completed_task is not None and completed_task.user_id is not None:
                user = user_repo.get_by_id(completed_task.user_id)
                if user is not None:
                    free_tier_gate.release_concurrency(user)
            if transcription_succeeded and completed_task is not None:
                usage_writer.record(
                    user_id=completed_task.user_id,
                    task_uuid=completed_task.uuid,
                    gpu_seconds=duration_observed,
                    file_seconds=completed_task.audio_duration or 0.0,
                    model=task_model,
                )
    # context exit — db.close() runs automatically; no manual boilerplate
```

ONE Session for the worker (single connection). Context manager closes it on the way out — even on exception. Zero try/finally session.close() lines.

### Example 4: Test fixture migration (T-19-XX per integration test)

**BEFORE (current `tests/integration/test_account_routes.py`):**
```python
# Old pattern — overrides container.db_session_factory
container = Container()
container.db_session_factory.override(providers.Factory(session_factory))
# ... build app, mount routers, register middleware ...
```

**AFTER (Phase 19):**
```python
# New pattern — overrides get_db via app.dependency_overrides
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_db

@pytest.fixture
def test_db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(test_db_engine):
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

**Singleton override (e.g., to stub csrf_service):**
```python
def override_csrf_service():
    return StubCsrfService()

app.dependency_overrides[get_csrf_service] = override_csrf_service
```

[CITED: https://fastapi.tiangolo.com/tutorial/testing/]

## State of the Art

| Old Approach | Current Approach (post-Phase-19) | Why Changed |
|--------------|------------------------------|-------------|
| `dependency-injector` library + `Container` + `Factory`/`Singleton` providers | FastAPI native `Depends` + `@lru_cache(maxsize=1)` factories | Stdlib only; no DI graph to maintain; `Depends` cache shares one Session per request automatically |
| Auth as `BaseHTTPMiddleware` setting `request.state.user` + global `PUBLIC_ALLOWLIST` | Per-route `Depends(authenticated_user)` with opt-in | Public routes don't include the dep — no allowlist regression risk; per-route security in OpenAPI schema |
| CSRF as `BaseHTTPMiddleware` reading `request.state.auth_method` | `Depends(csrf_protected)` chained off `Depends(authenticated_user)` | Composable with auth; no implicit `request.state` couple |
| `_container.X()` reach-in from middleware/WS/background | Module singletons (`@lru_cache`) + explicit `with SessionLocal() as db:` block | Background scope has no Request — context manager is the SQLAlchemy-native pattern |
| Manual `try/finally service.repository.session.close()` per provider | ONE `try/finally session.close()` inside `get_db` | FastAPI dep cache: one Session per request, shared across all sub-deps, closed automatically |
| Test fixture override via `container.db_session_factory.override(...)` | `app.dependency_overrides[get_db] = lambda: fixture_session` | FastAPI-native; clears via `app.dependency_overrides.clear()`; works without DI library |
| `AUTH_V2_ENABLED` flag + dual middleware stacks | Single auth path via Depends | Phase 13 cutover is done; flag is dead weight |

**Deprecated/outdated (after Phase 19):**

- `app/core/container.py`: deleted.
- `app/core/dual_auth.py`: deleted.
- `app/core/csrf_middleware.py`: deleted.
- `app/core/auth.py` (BearerAuthMiddleware): deleted.
- `is_auth_v2_enabled()` helper in `app/core/feature_flags.py`: deleted.
- `dependency-injector` PyPI package: removed from `pyproject.toml`.
- `set_container()` helper in `app/api/dependencies.py`: deleted.
- `_container` global variable: deleted.
- `PUBLIC_ALLOWLIST`, `PUBLIC_PREFIXES`, `_is_public`, `_set_state_anonymous` in dual_auth.py: deleted.
- `tests/fixtures/test_container.py` (TestContainer subclass): deleted (replaced with `app.dependency_overrides` pattern).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (backend); vitest + Playwright (frontend) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (verify); `frontend/vitest.config.ts`; `frontend/playwright.config.ts` |
| Quick run command | `.venv/Scripts/python.exe -m pytest tests/ -x --tb=short` (backend); `cd frontend && bun run test` (frontend unit) |
| Full suite command | `.venv/Scripts/python.exe -m pytest tests/ --tb=short` then `cd frontend && bun run test && bun run test:e2e` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REFACTOR-01 | Zero `_container.` callsites | static-grep | `grep -rn '_container\.' app/` returns 0 | ✅ Wave 0 (`scripts/verify_no_container.sh` or shell one-liner in CI) |
| REFACTOR-02 | Zero `session.close()` outside `get_db` | static-grep | `grep -rn 'session\.close()' app/` returns ≤ 1 (only in `get_db`) | ✅ Wave 0 |
| REFACTOR-03 | Single auth path via Depends; bearer wins; sliding cookie | integration | `pytest tests/integration/test_auth_routes.py tests/integration/test_jwt_attacks.py tests/integration/test_security_matrix.py -x` | ✅ exists; needs fixture rewrite (override pattern) |
| REFACTOR-04 | `AUTH_V2_ENABLED` + `BearerAuthMiddleware` deleted | static-grep | `grep -rn 'AUTH_V2_ENABLED\|is_auth_v2_enabled\|BearerAuthMiddleware\|DualAuthMiddleware' app/` returns 0 | ✅ Wave 0 |
| REFACTOR-05 | `dependency_injector` removed | static-grep + import probe | `grep -rn 'dependency_injector' app/ tests/` returns 0; `python -c "import dependency_injector"` after `uv sync` raises ModuleNotFoundError | ✅ Wave 0 |
| REFACTOR-06 | Test count = baseline | collection diff | `pytest --collect-only -q > /tmp/post.txt; diff tests/baseline_phase19.txt /tmp/post.txt` empty (or +new tests only) | ❌ baseline created in T-19-01 |
| REFACTOR-07 | Set-Cookie attrs byte-identical | e2e | `cd frontend && bun run test:e2e` (Playwright captures Set-Cookie via `response.headers()`) | ✅ Phase-15 e2e suite covers cookie + redirect |
| (new) | No connection-pool leak | integration | `pytest tests/integration/test_no_session_leak.py -v` — 50 sequential GET /api/account/me each <100ms | ❌ Wave 0 — NEW FILE T-19-13 |
| (new) | Auth dep handles bearer-wins-cookie | integration | `pytest tests/integration/test_auth_dep.py` (or extend `test_security_matrix.py`) — request with BOTH headers + cookie, verify bearer leg ran | ❌ Wave 0 — extend existing OR new file |
| (new) | Sliding cookie refresh on every authed cookie request | integration | First request login → record `Set-Cookie: session=A`; second request with cookie A → record `Set-Cookie: session=B`; assert B ≠ A but both valid JWTs | ❌ Wave 0 — extend `test_auth_routes.py` |
| (new) | Anonymous request to `/auth/login` after stale cookie | integration | Request with bad cookie + valid login body → 200 (recovery flow not blocked) | ❌ Wave 0 — extend `test_auth_routes.py` |
| (new) | Public allowlist replaced by per-route opt-in | static-audit | Each public route (`/health`, `/health/live`, `/health/ready`, `/`, `/openapi.json`, `/docs`, `/redoc`, `/static/*`, `/auth/register`, `/auth/login`, `/auth/logout`, `/billing/webhook`, `/uploads/files/*`) does NOT include `Depends(authenticated_user)` | manual checklist in T-19-15 |

### Sampling Rate

- **Per task commit:** `pytest tests/integration/test_<changed_module>.py -x` (target affected test files; Vitest runs only when frontend touched, which it isn't in this phase).
- **Per wave merge:** `pytest tests/ --tb=short` (full backend suite).
- **Phase gate:** Full backend + `bun run test` + `bun run test:e2e` green before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `tests/integration/test_no_session_leak.py` — covers REFACTOR + the original bug class. NEW FILE T-19-13.
- [ ] `tests/integration/test_auth_dep.py` (or section in `test_security_matrix.py`) — covers bearer-wins, sliding refresh, stale-cookie recovery, optional-user variant. NEW FILE/SECTION T-19-04.
- [ ] `tests/integration/conftest.py` — shared fixtures: `client(test_db_engine)`, autouse `_clear_overrides`, autouse `_clear_lru_caches`. NEW FILE T-19-03 OR extend existing `tests/conftest.py`.
- [ ] `tests/baseline_phase19.txt` — `pytest --collect-only -q` snapshot. T-19-01.
- [ ] Migrate ALL 14 existing integration tests from `container.db_session_factory.override(...)` to `app.dependency_overrides[get_db] = override_get_db`. Files (verified by grep):
  - `tests/integration/test_account_routes.py`
  - `tests/integration/test_auth_routes.py` (2 callsites)
  - `tests/integration/test_billing_routes.py`
  - `tests/integration/test_csrf_enforcement.py`
  - `tests/integration/test_free_tier_gate.py`
  - `tests/integration/test_jwt_attacks.py`
  - `tests/integration/test_key_routes.py`
  - `tests/integration/test_per_user_scoping.py`
  - `tests/integration/test_phase11_di_smoke.py` (this becomes `test_phase19_di_smoke.py` — DI structural test must change)
  - `tests/integration/test_security_matrix.py`
  - `tests/integration/test_task_routes.py`
  - `tests/integration/test_ws_ticket_flow.py`
  - `tests/integration/test_ws_ticket_safety.py`
  - Plus `tests/fixtures/test_container.py` (DELETE FILE — class inheritance from Container goes away).
- [ ] Framework install: NONE — all already in `pyproject.toml [project.optional-dependencies] dev`.

## Project Constraints (from CLAUDE.md)

| Directive | Source | Phase 19 Implication |
|-----------|--------|----------------------|
| **Backend `uv` for venv** | Stack section | All commands use `.venv/Scripts/python.exe` and `uv sync` for lock regen. |
| **Frontend bun-only** | Package Manager section | Phase 19 is backend-only — no frontend deps touched. Verifier still runs `cd frontend && bun run test && bun run test:e2e` for REFACTOR-07. |
| **Three-tier test strategy** | Test Strategy section | Backend pytest is the primary surface. Vitest unit + Playwright e2e are regression gates only — no new e2e specs needed (Phase 15 specs cover the cookie/redirect surface that REFACTOR-07 protects). |
| **DRY** | Code Quality section | ONE `get_db`. ONE `authenticated_user`. ONE `csrf_protected`. Zero duplicated session-close boilerplate. |
| **SRP** | Code Quality section | `get_db` owns Session lifecycle ONLY. `authenticated_user` owns auth resolution ONLY. `csrf_protected` owns CSRF check ONLY. Routes own HTTP I/O ONLY. Services own business logic ONLY. |
| **Tiger-style** | Code Quality section | Boundary asserts: `_resolve_bearer` early-returns None on every failure leg (not nested-if). `_resolve_cookie` ditto. `csrf_protected` early-returns on bypass cases (GET, bearer, anon). |
| **No nested-if spaghetti** | Code Quality section | Verifier grep gate on every Phase 19 commit: `grep -cE "^\s+if .*\bif\b" app/api/dependencies.py app/main.py app/core/services.py` returns 0. |
| **Self-explanatory names** | Code Quality section | `authenticated_user`, `authenticated_user_optional`, `csrf_protected`, `get_db` (FastAPI canonical), `get_password_service` (verb-prefix is FastAPI Depends idiom). |
| **Subtype-first error handling** | Code Quality section | `_resolve_bearer` catches `_BEARER_FAILURES = (InvalidApiKeyFormatError, InvalidApiKeyHashError)` — both subtypes of nothing dangerous, but the principle holds for `_COOKIE_DECODE_FAILURES` ordering: `JwtExpiredError` checked specifically before generic `ValueError`. |
| **apiClient is the sole non-WS network entry** (UI-11) | Cookie/Conventions section | Frontend untouched — invariant preserved by phase scope (REFACTOR-07). |
| **401 redirect logic** | Conventions section | Phase 19 preserves the `WWW-Authenticate: Bearer realm="whisperx"` header on 401 — frontend redirect logic depends on the body shape `{"detail":"Authentication required"}` which is byte-identical pre/post (verified — see verification gate 7 in CONTEXT). |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FastAPI 0.128.0 (currently pinned) is at-or-after 0.82.0 — anyio thread-pool deadlock fix is included | Q1 / Pitfall 2 | If wrong (downgrade) sync `Depends` chains might deadlock under load. **Mitigation:** version is pinned in `pyproject.toml:32`. [VERIFIED: `pyproject.toml` line 32] |
| A2 | All ML services (`WhisperX*Service`) are stateless POST-construction — moving them to `@lru_cache(maxsize=1)` factories is safe | Pattern 4 / Q3 | If wrong (instance state mutated per request) tests would intermittently fail. **Mitigation:** existing `Container` already declares them as `Singleton` — same lifecycle. [CITED: `app/core/container.py:173-188`] |
| A3 | `slowapi` `@limiter.limit` decorator works correctly when route signature is unchanged but `Depends` chain changes | Pitfall 5 | If wrong, `/auth/register` 3/hr and `/auth/login` 10/hr rate limits silently break. **Mitigation:** Phase-13 tests for rate-limit assertion still run; verification gate 7 catches. |
| A4 | The 14 integration test files can all be migrated to `app.dependency_overrides[get_db]` without behavior change | Wave 0 Gaps | If wrong, REFACTOR-06 trips (test count regression). **Mitigation:** baseline snapshot at T-19-01 catches any silent loss. |
| A5 | Sliding cookie refresh works inside `Depends(authenticated_user)` for routes that DON'T return their own `Response` | Pattern 4 | If wrong, the cookie attribute is silently lost on the wire. **Mitigation:** Playwright e2e (REFACTOR-07) compares Set-Cookie attrs byte-identical pre/post. Backed by [CITED: FastAPI yield-deps tutorial diagram]. |
| A6 | Test fixture override via `app.dependency_overrides[get_db] = override` propagates correctly to nested deps (e.g., `get_user_repository` which depends on `get_db`) | Example 4 / Wave 0 Gaps | If wrong, the test sees real DB while the fixture session is unused. **Mitigation:** [CITED: FastAPI testing tutorial confirms transitive override applies — overrides propagate through the cache]. |
| A7 | `dependency-injector` 4.41.0 has no other transitive consumer in the repo (only `app/core/container.py`) | Stack section | If wrong, removing the package from `pyproject.toml` breaks an importer. **Mitigation:** verifier `grep -rn 'dependency_injector' app/ tests/` after package-removal commit catches. [VERIFIED: existing grep — only `app/core/container.py:1` and `tests/fixtures/test_container.py:3` reference it; both deleted.] |
| A8 | The existing `app/core/feature_flags.py` has no other consumers besides `is_auth_v2_enabled` | D3 | If wrong, deleting `is_auth_v2_enabled` breaks importers. **Mitigation:** verifier grep catches. [VERIFIED: codebase grep — only `app/main.py:61, 198, 247, 257` consume it.] |

## Open Questions

1. **Should `app/core/services.py` import ML services lazily?**
   - What we know: Phase 12 CLI commands and migrations don't load ML models — they avoid touching ML services entirely. With `@lru_cache(maxsize=1)`, the model load defers to first call, which is fine.
   - What's unclear: import-time side effects in `app.infrastructure.ml.__init__.py` could still fire when `app/core/services.py` imports `WhisperXTranscriptionService`. Need to verify.
   - Recommendation: import lazily inside the factory function:
     ```python
     @lru_cache(maxsize=1)
     def get_transcription_service():
         from app.infrastructure.ml import WhisperXTranscriptionService
         return WhisperXTranscriptionService()
     ```
     Two-line tradeoff for safety. Planner decides.

2. **What happens to the `tests/fixtures/test_container.py` `MockTranscriptionService` etc.?**
   - What we know: `TestContainer` subclass overrides ML services with mocks. Once `Container` is gone, this file is dead.
   - What's unclear: which existing tests rely on the mock ML services via `test_container` fixture vs which use direct `app.dependency_overrides`. Audit needed in T-19-NN per-test migration.
   - Recommendation: at T-19-NN per-test migration, replace `test_container` fixture usage with `app.dependency_overrides[get_transcription_service] = lambda: MockTranscriptionService()` style. Move mock classes to `tests/mocks/` (already exists per file listing — minor reorg). DELETE `test_container.py` at end-of-phase.

3. **Should `_resolve_authenticated_user_id` (current helper at `dependencies.py:306`) be deleted or kept?**
   - What we know: it's used by `get_scoped_task_repository` (`dependencies.py:333`) and `get_scoped_task_management_service` (`dependencies.py:355`) for per-user scoping defence-in-depth.
   - What's unclear: in the new world, the route signs `user: User = Depends(authenticated_user), repo: ITaskRepository = Depends(get_task_repository)` and the route itself calls `repo.set_user_scope(user.id)` — explicit, no defence-in-depth needed. OR: keep a `get_scoped_task_repository` helper that takes `user: User = Depends(authenticated_user)` and applies the scope automatically.
   - Recommendation: keep `get_scoped_task_repository` and `get_scoped_task_management_service` post-refactor — they're idiomatic Depends chains in the new world. Drop `_resolve_authenticated_user_id` since `Depends(authenticated_user)` IS the resolution. Effective sig:
     ```python
     def get_scoped_task_repository(
         user: User = Depends(authenticated_user),
         db: Session = Depends(get_db),
     ) -> ITaskRepository:
         repo = SQLAlchemyTaskRepository(db)
         repo.set_user_scope(int(user.id))
         return repo
     ```

4. **`/billing/webhook` is "public" today (Stripe HMAC, no auth) — how should this be modeled?**
   - What we know: today it's in `PUBLIC_ALLOWLIST`. After Phase 19, public means "doesn't include `Depends(authenticated_user)`" — naturally satisfied. Stripe HMAC verification is a v1.3 concern (currently a stub).
   - Recommendation: route stays auth-free; T-19-15 sweep verifies it doesn't accidentally inherit a router-level `Depends(authenticated_user)`. Add an explicit `# Stripe webhook — auth via HMAC (v1.3)` comment at the route declaration.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All backend | ✓ (verified pyproject) | requires-python >=3.10 | — |
| `uv` | Lockfile regen | ✓ (project standard) | n/a | `pip uninstall dependency-injector` works as one-shot if `uv` unavail |
| `fastapi` 0.128.0 | All routes | ✓ (pinned) | 0.128.0 | — |
| `sqlalchemy` 2.x | All DB | ✓ | 2.x | — |
| `slowapi` >=0.1.9 | Rate limit decorators | ✓ | >=0.1.9 | — |
| `pyjwt` >=2.8.0 | JWT codec | ✓ | >=2.8.0 | — |
| `argon2-cffi` >=23.1.0 | Password hash | ✓ | >=23.1.0 | — |
| Frontend `bun` | REFACTOR-07 e2e gate | ✓ (per CLAUDE.md project standard) | n/a | — |
| Playwright Chromium | REFACTOR-07 | ✓ (per Phase 15 e2e suite) | n/a | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Sources

### Primary (HIGH confidence)
- FastAPI SQL Databases tutorial — https://fastapi.tiangolo.com/tutorial/sql-databases/ — canonical `get_session` yield/finally pattern
- FastAPI Dependencies-with-yield tutorial — https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/ — lifecycle ordering (response sent BEFORE finally runs)
- FastAPI Settings advanced tutorial — https://fastapi.tiangolo.com/advanced/settings/ — `@lru_cache` canonical pattern + dependency_overrides usage
- FastAPI Testing tutorial — https://fastapi.tiangolo.com/tutorial/testing/ — `app.dependency_overrides` pattern + cleanup
- FastAPI Security Tools — https://fastapi.tiangolo.com/reference/security/ — auto_error=False optional auth pattern
- Codebase: `.planning/debug/login-correct-pw-30s-401.md` — already-completed root-cause analysis (15-leak threshold + 30s pool timeout EXACTLY reproduces in `.venv` simulation)
- Codebase: `app/api/dependencies.py`, `app/core/dual_auth.py`, `app/core/csrf_middleware.py`, `app/core/container.py`, `app/main.py`, `app/services/whisperx_wrapper_service.py`, `app/api/websocket_api.py`, `app/api/ws_ticket_routes.py` — verified Read 2026-05-02
- Codebase: `scripts/verify_session_leak_fix.py` — proves both class-1 (Depends) and class-2 (direct-container) leaks reproduce in 30 iterations

### Secondary (MEDIUM confidence)
- GitHub Discussion fastapi/fastapi #6628 — sync Depends + SQLAlchemy thread-pool deadlock (resolved 0.82.0+; whisperX uses 0.128.0)
- testdriven.io: FastAPI with Async SQLAlchemy + Alembic — https://testdriven.io/blog/fastapi-sqlmodel/
- chaoticengineer.hashnode.dev: Patterns and Practices for using SQLAlchemy 2.0 with FastAPI

### Tertiary (LOW confidence)
- Various community blogs on singleton patterns — used only to confirm no contradictory advice; primary recommendation backed by official FastAPI docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against `pyproject.toml`; no new packages introduced (only one removed); FastAPI 0.128.0 confirmed past the anyio deadlock fix.
- Architecture: HIGH — patterns mapped 1:1 against official FastAPI tutorials; codebase reality fully audited (every `_container.X()` callsite enumerated; every `session.close()` callsite enumerated).
- Pitfalls: HIGH — Pitfalls 1-2 documented in official FastAPI tutorial diagrams; Pitfall 8 (deletion order) directly informs the 16-step T-19-NN sequence; Pitfall 6-7 backed by FastAPI testing tutorial.
- Q1-Q3 answers: HIGH — each answer is backed by both (a) FastAPI official tutorial CITED quote and (b) codebase grep confirmation that the recommendation aligns with existing structure.

**Research date:** 2026-05-02
**Valid until:** 2026-05-30 (30-day stable window for FastAPI 0.128.0 / SQLAlchemy 2.x patterns; longer if Phase 20 doesn't migrate to async)

## RESEARCH COMPLETE

**Phase:** 19 - Auth + DI Structural Refactor
**Confidence:** HIGH

### Key Findings

- The fix is mechanical structural replacement — every `_container.X()` callsite has a verified canonical FastAPI 2026 idiom (Depends chain or @lru_cache singleton), with ZERO open architectural questions in CONTEXT.
- Sliding cookie refresh works correctly inside `Depends(authenticated_user)` because FastAPI's documented yield-dep lifecycle places `response` serialization BEFORE the dep's `finally` block — pre-yield `response.set_cookie(...)` lands on the wire.
- The 16-step `T-19-NN` order in CONTEXT is sound: each step leaves the suite green because new helpers coexist with old `_container.X()` callsites until `container.py` itself is deleted in T-19-12 (the LAST structural step before regression and frontend e2e).
- Test migration is the largest single chunk: 14 integration test files plus the `TestContainer` subclass need conversion from `container.db_session_factory.override(...)` to `app.dependency_overrides[get_db] = ...`. This is mechanical but high-volume — plan should allocate a wave of tasks for it.
- Background-task and WebSocket scopes use explicit `with SessionLocal() as db:` blocks — the context manager's `__exit__` is the close path; ZERO manual `session.close()` lines in the new code.

### File Created

`C:\laragon\www\whisperx\.planning\phases\19-auth-di-refactor\19-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | All deps already pinned in pyproject.toml; only `dependency-injector` removed; no version probes needed. |
| Architecture | HIGH | Every pattern backed by FastAPI official tutorial; codebase reality fully audited. |
| Pitfalls | HIGH | Pitfalls 1-3 backed by FastAPI tutorial diagrams; Pitfall 8 directly informs the locked T-19-NN order. |
| Q1-Q3 answers | HIGH | Each answer is backed by both an official FastAPI doc citation AND a codebase grep confirmation. |
| Validation Architecture | HIGH | All 14 existing integration tests enumerated by grep; 4 new test files identified; per-task and per-wave gates specified verbatim. |

### Open Questions (for planner — non-blocking)

1. Lazy-import ML services in `app/core/services.py` (recommended: yes, keeps CLI/migration paths free of model load).
2. `tests/fixtures/test_container.py` migration target — recommended: per-test inline `app.dependency_overrides`.
3. Keep `get_scoped_task_repository` helper (recommended: yes; idiomatic chain off `Depends(authenticated_user)`).
4. `/billing/webhook` opt-out — recommended: explicit comment at route declaration.

### Ready for Planning

Research complete. Planner can now create per-task PLAN.md files for T-19-01 through T-19-16 verbatim from CONTEXT's locked execution order, with each task's verification surface mapped in the Validation Architecture section above.

Sources:
- [FastAPI SQL Databases tutorial](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [FastAPI Dependencies with yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)
- [FastAPI Settings advanced (lru_cache)](https://fastapi.tiangolo.com/advanced/settings/)
- [FastAPI Testing tutorial](https://fastapi.tiangolo.com/tutorial/testing/)
- [FastAPI Security Tools](https://fastapi.tiangolo.com/reference/security/)
- [GitHub Discussion fastapi/fastapi #6628 — sync Depends deadlock](https://github.com/fastapi/fastapi/discussions/6628)
- [testdriven.io FastAPI + SQLAlchemy](https://testdriven.io/blog/fastapi-sqlmodel/)
