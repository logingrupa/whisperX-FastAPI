# Architecture Research: v1.2 Multi-User Auth + API Keys + Billing-Ready

**Domain:** Auth/keys/billing layer bolted onto existing WhisperX FastAPI + React app
**Researched:** 2026-04-29
**Confidence:** HIGH (codebase grep verified, patterns match existing DI/repo conventions)

---

## TL;DR — Build Order

1. **DB + Alembic baseline** (no behavior change). `app/infrastructure/database/models.py` adds User/ApiKey/Subscription/UsageEvent. Alembic init + stamp existing schema as baseline. Add `user_id` FK to `tasks` (NULLABLE first, backfill, then NOT NULL).
2. **Domain + repos + DI providers** (no routes yet). `IUserRepository`, `IApiKeyRepository`, `IRateLimitRepository`. Wire into `Container`.
3. **Auth services** (pure logic, no HTTP). `AuthService` (register/login/session), `KeyService` (hash/verify `whsk_*`), `RateLimitService` (token bucket).
4. **Replace middleware** at `app/core/auth.py` — single `DualAuthMiddleware` (session OR bearer) sets `request.state.user` + `plan_tier`. Existing `BearerAuthMiddleware` deleted.
5. **Auth routes** `app/api/auth_api.py`, `app/api/account_api.py`, `app/api/keys_api.py`. Mount in `app/main.py`.
6. **Per-user task scoping** — repository filters by `user_id` from `request.state.user`. Update `task_api.py`, `audio_api.py`, `tus_upload_api.py`, `streaming_upload_api.py`.
7. **WebSocket auth** via `Sec-WebSocket-Protocol` subprotocol. Update `websocket_api.py`.
8. **CSRF dependency** — `Depends(verify_csrf)` on session-auth state-mutating routes.
9. **Admin CLI** `app/cli.py`. Bootstrap admin + backfill orphan tasks.
10. **Frontend router shell** — `BrowserRouter` in `main.tsx`, `App.tsx` becomes routes + outlet. Auth context, `apiClient` wrapper.
11. **Frontend auth pages** — `/ui/login`, `/ui/register`, `/ui/dashboard/keys`, `/ui/dashboard/usage`. Protected route guard.
12. **Wire existing API clients** through `apiClient` (`taskApi`, `transcriptionApi`, `tusUpload`, websocket subprotocol).

Steps 1-3 ship as silent infrastructure. Step 4 is the cutover — must ship with steps 5-7 and frontend (steps 10-12) atomically or app breaks for users.

---

## Existing Architecture Map (verified by grep)

```
Request flow today:
  Client
    -> Starlette ASGI
    -> CORSMiddleware (allow_origins=*)
    -> BearerAuthMiddleware     # app/core/auth.py — single env token
    -> Router                   # app/api/{stt,task,service,websocket,
    -> Endpoint                 #     streaming_upload,tus_upload}_api.py
    -> Depends(get_*_repository) -> Container.task_repository()
    -> Repo (SQLAlchemy session)
    -> SQLite records.db (single tasks table)
```

- DI: `app/core/container.py` — `dependency-injector` lib, Singleton + Factory providers.
- DI bridge: `app/api/dependencies.py` — module-global `_container`, `set_container()` called in `main.py` line 56.
- Repo iface: `app/domain/repositories/task_repository.py` (`ITaskRepository`).
- Repo impl: `app/infrastructure/database/repositories/sqlalchemy_task_repository.py`.
- Schema: `Base.metadata.create_all(bind=engine)` at `main.py:48` — **no Alembic yet**.
- WebSocket: `app/api/websocket_api.py:23` — `/ws/tasks/{task_id}`, no auth check.
- Frontend: single-page `App.tsx`, no router, raw `fetch('/task/...')` and `fetch('/speech-to-text...')`.
- Frontend API base: relative URLs always (`getApiBaseUrl()` returns `''`). Same-origin in prod via FastAPI SPA mount.

---

## Recommended Architecture — v1.2 Request Flow

```
Browser request (UI)                    External API client
  cookie: session=<jwt>                   Authorization: Bearer whsk_...
  X-CSRF-Token: <token>                   (no cookie, no CSRF)
        |                                       |
        +------------------+--------------------+
                           v
              CORSMiddleware (unchanged)
                           v
              DualAuthMiddleware            <-- replaces BearerAuthMiddleware
                - resolve user from cookie OR bearer
                - set request.state.user, .plan_tier, .auth_method
                - 401 on missing/invalid (except public paths)
                           v
              Route -> Depends(verify_csrf) [session-only routes]
                    -> Depends(rate_limit)  [per-user, per-key]
                    -> Depends(get_task_repository_scoped)
                           v
              Repo filters by request.state.user.id
                           v
              SQLite (WAL on)
```

WebSocket flow:
```
ws connect /ws/tasks/{task_id}
  Sec-WebSocket-Protocol: whisperx.bearer.<token>      (or session cookie)
        v
  websocket_api.py
    accept(subprotocol=...) only after token verified
    + verify task.user_id == authed user.id
        v
  connection_manager.connect()
```

---

## 1. Where Auth Middleware Lives

**Decision:** Replace `BearerAuthMiddleware` in-place at `app/core/auth.py`. Same import path, same registration site (`main.py:169`).

**Why in-place:**
- `BearerAuthMiddleware` is the *concept* of auth middleware. v1.2 expands what it accepts. Same role.
- Tests, mocks, env-var docs reference `app.core.auth`. Renaming churns more than the value.
- File is 79 lines today — replace whole file with new `DualAuthMiddleware` class. `BearerAuthMiddleware` name retained as alias for backward compat or deleted (recommend delete — clean cutover).

**File changes:**
- MODIFY `app/core/auth.py` — new class `DualAuthMiddleware`, helpers `_resolve_session()`, `_resolve_bearer()`, `_set_request_state()`.
- MODIFY `app/main.py:30,169` — import + register `DualAuthMiddleware`.
- DELETE env var `API_BEARER_TOKEN` from docs (kept in code as no-op fallback if needed for rollback — but recommend hard cut).

**`request.state` contract** (set by middleware before handler):
```python
request.state.user: User              # domain entity (id, email, plan_tier, ...)
request.state.plan_tier: PlanTier     # enum: FREE | TRIAL | PRO
request.state.auth_method: str        # "session" | "bearer"
request.state.api_key_id: str | None  # set when auth_method == "bearer"
```

Handlers and repos pull `request.state.user` via dependency `Depends(current_user)` (new helper in `app/api/dependencies.py`).

---

## 2. Cookie Session + Bearer Dual-Auth Flow

**Decision:** ONE middleware, two resolution paths. Not two stacked middlewares.

**Why one:**
- ASGI middleware chain is fragile to ordering. Two auth middlewares = duplicate 401 logic, duplicate public-path lists, race for `request.state`.
- Single class = single source of truth for "is this request authenticated and who is it".
- Bearer path runs first (header check is O(1) string compare); session path is fallback.

**Resolution order in `dispatch`:**
```
1. if request.method == "OPTIONS": pass through (CORS preflight)
2. if path in PUBLIC_PATHS: pass through (no state set; downstream handles "anonymous")
3. if Authorization: Bearer whsk_...:
     -> KeyService.verify(token) -> User
     -> set state, auth_method="bearer"; continue
     -> on miss: 401 Bearer
4. elif cookie "session" present:
     -> SessionService.verify_jwt(cookie) -> User (sliding renewal: re-Set-Cookie if >1d remaining)
     -> set state, auth_method="session"; continue
     -> on miss: clear cookie, 401 Session
5. else:
     -> path is private -> 401 (NoCredentials)
```

**Public paths** (extend existing `PUBLIC_PATH_PREFIXES` tuple):
```python
PUBLIC_PATHS = (
    "/health", "/openapi.json", "/docs", "/redoc",
    "/static", "/favicon.ico",
    "/ui",                          # SPA shell — auth gating happens client-side
    "/api/auth/register",           # public — IP rate-limited at handler
    "/api/auth/login",              # public — IP rate-limited at handler
    "/api/auth/csrf",               # public — issues CSRF token + session bootstrap
)
```

**OPTIONS:** always allowed (preflight). Unchanged from existing middleware.

**Anti-pattern:** Putting CSRF check inside this middleware. CSRF is route-level (Depends), not middleware-level — bearer routes must skip CSRF, and only the route knows its auth_method.

---

## 3. WebSocket Auth Integration

**Decision:** **Subprotocol-based bearer** (`Sec-WebSocket-Protocol` header). Cookie auto-attached by browser as fallback for same-origin session auth.

**Why subprotocol over query string:**
- Query strings logged by proxies, in browser history, in nginx access logs. Tokens in URLs = secret leakage.
- Subprotocol header is what proxies/CDNs are designed to forward without logging payload.
- Browser `WebSocket` constructor accepts subprotocols as second arg — clean API.
- Cookie alone insufficient for external API clients (no browser).

**Why not "first message"** (send token as JSON after connect):
- Connection accepted before auth = DoS vector (attacker holds open connection, server allocates resources).
- Race conditions: server sends queued messages before client sends token.

**Server pattern** (`app/api/websocket_api.py`):
```python
@websocket_router.websocket("/ws/tasks/{task_id}")
async def websocket_task_progress(
    websocket: WebSocket,
    task_id: str,
    user: User = Depends(get_websocket_user),  # new dep
):
    # get_websocket_user reads:
    #   1. websocket.headers.get("sec-websocket-protocol") -> parse "whisperx.bearer.<token>"
    #   2. websocket.cookies.get("session") -> verify JWT
    # Raises WebSocketException(code=1008) on miss
    # accept() WITH the matched subprotocol (echo back) for spec compliance:
    await websocket.accept(subprotocol="whisperx.bearer")

    # Verify task ownership
    task = task_repo.get_by_id(task_id)
    if task.user_id != user.id:
        await websocket.close(code=1008, reason="forbidden")
        return
    ...
```

**Client pattern** (`frontend/src/hooks/useTaskProgress.ts`):
```typescript
// Browser: cookie auto-attached, no subprotocol needed for session auth
const ws = new WebSocket(`${baseUrl}/ws/tasks/${taskId}`);

// External API client: subprotocol with bearer
const ws = new WebSocket(
  `${baseUrl}/ws/tasks/${taskId}`,
  [`whisperx.bearer.${apiKey}`]
);
```

**FastAPI WebSocket `Depends`:** supported since 0.65+; documented pattern. `app/api/websocket_api.py:24` already takes `task_id` path param — adding `Depends` parameter is a one-line change.

**File changes:**
- MODIFY `app/api/websocket_api.py` — add `Depends(get_websocket_user)`, ownership check.
- NEW helper in `app/api/dependencies.py` — `async def get_websocket_user(websocket: WebSocket) -> User`.

---

## 4. Per-User Task Scoping

**Decision:** `user_id` FK on `tasks` table. Filter at **repository layer**, not middleware.

**Why repo layer (clean):**
- Repository owns data access. "User can only see their tasks" is a data invariant, not a transport concern.
- Single place to enforce. Middleware injection (rewriting query strings or filter args) is opaque, hard to test, breaks LSP for `ITaskRepository`.
- DI gives natural seam: repository constructed with `user_id` from request scope.

**Implementation pattern (extends existing factory):**
```python
# app/core/container.py
task_repository = providers.Factory(
    SQLAlchemyTaskRepository,
    session=db_session_factory,
)

# app/api/dependencies.py — NEW scoped variant
def get_task_repository_scoped(
    request: Request,
) -> Generator[ITaskRepository, None, None]:
    repo = _container.task_repository()
    repo.set_user_scope(request.state.user.id)  # OR construct fresh with user_id
    yield repo
```

`SQLAlchemyTaskRepository` adds a `_user_id: int | None` slot. All queries `.filter(ORMTask.user_id == self._user_id)` when set. Admin-mode bypass: when scope is None, no filter applied (admin CLI uses this).

**Migration strategy for existing rows:**
1. Add `user_id` column NULLABLE (Alembic migration). No backfill yet.
2. Admin CLI command `python -m app.cli create-admin --email ... --password ...` creates first user.
3. Admin CLI command `python -m app.cli backfill-tasks --owner <admin-email>` UPDATEs all `tasks` WHERE `user_id IS NULL` → admin user id.
4. Follow-up Alembic migration: `ALTER COLUMN user_id NOT NULL`. SQLite needs table-rebuild for NOT NULL — Alembic batch ops handle this (`batch_alter_table`).

**FK behavior:**
- `ON DELETE CASCADE` — when account deleted via `DELETE /api/account/data`, all owned tasks vanish. Same migration adds `ondelete="CASCADE"`.
- Cascade also covers `ApiKey`, `Subscription`, `UsageEvent`.

**File changes:**
- MODIFY `app/infrastructure/database/models.py` — add `user_id` FK on `Task`, plus new `User`, `ApiKey`, `Subscription`, `UsageEvent` models.
- MODIFY `app/infrastructure/database/repositories/sqlalchemy_task_repository.py` — `set_user_scope()` + filter.
- MODIFY `app/domain/entities/task.py` — add `user_id` field.
- MODIFY `app/api/dependencies.py` — replace `get_task_repository` with scoped variant; admin endpoints get unscoped variant.

---

## 5. DI Container Additions

**Decision:** Mirror existing pattern exactly. New providers parallel to `task_repository` / `task_management_service`.

**Why mirror:**
- `app/core/container.py` is a flat declarative container. Consistency wins over cleverness.
- Reviewers can compare new providers to `task_repository` line-by-line.

**Additions to `Container`:**
```python
# app/core/container.py (extends existing)

# Repositories — Factory with session
user_repository = providers.Factory(
    SQLAlchemyUserRepository, session=db_session_factory,
)
api_key_repository = providers.Factory(
    SQLAlchemyApiKeyRepository, session=db_session_factory,
)
rate_limit_repository = providers.Factory(
    SQLAlchemyRateLimitRepository, session=db_session_factory,
)
subscription_repository = providers.Factory(
    SQLAlchemySubscriptionRepository, session=db_session_factory,
)

# Services — stateless = Singleton, stateful = Factory
password_service = providers.Singleton(
    Argon2PasswordService,
    time_cost=config.provided.auth.ARGON2_TIME_COST,
    memory_cost=config.provided.auth.ARGON2_MEMORY_COST,
)
token_service = providers.Singleton(
    JwtTokenService,
    secret=config.provided.auth.JWT_SECRET,
    ttl_seconds=config.provided.auth.SESSION_TTL,
)
csrf_service = providers.Singleton(CsrfService, secret=...)

auth_service = providers.Factory(
    AuthService,
    user_repository=user_repository,
    password_service=password_service,
    token_service=token_service,
)
key_service = providers.Factory(
    KeyService,
    api_key_repository=api_key_repository,
    user_repository=user_repository,
)
rate_limit_service = providers.Factory(
    RateLimitService,
    repository=rate_limit_repository,
)
```

**`app/api/dependencies.py` additions:**
```python
def get_auth_service() -> Generator[AuthService, None, None]:
    yield _container.auth_service()

def get_key_service() -> Generator[KeyService, None, None]:
    yield _container.key_service()

def get_rate_limit_service() -> Generator[RateLimitService, None, None]:
    yield _container.rate_limit_service()

def current_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user

def verify_csrf(request: Request) -> None:
    # Skip if bearer auth (request.state.auth_method == "bearer")
    if request.state.auth_method == "bearer":
        return
    header = request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get("csrf")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise HTTPException(403, "CSRF check failed")

def rate_limit_dep(
    request: Request,
    rl: RateLimitService = Depends(get_rate_limit_service),
) -> None:
    rl.consume(user_id=request.state.user.id, plan_tier=request.state.plan_tier)
```

**File changes:**
- MODIFY `app/core/container.py` — append new providers.
- MODIFY `app/api/dependencies.py` — append new providers + `current_user`, `verify_csrf`, `rate_limit_dep`.
- NEW domain interfaces: `app/domain/repositories/{user,api_key,rate_limit,subscription}_repository.py`.
- NEW domain entities: `app/domain/entities/{user,api_key,subscription,usage_event}.py`.
- NEW services: `app/services/{auth_service,key_service,rate_limit_service,csrf_service}.py`.
- NEW infrastructure: `app/infrastructure/auth/{argon2_password_service.py,jwt_token_service.py}` and `app/infrastructure/database/repositories/sqlalchemy_{user,api_key,rate_limit,subscription}_repository.py`.

---

## 6. Alembic Baseline Strategy

**Problem:** Project currently uses `Base.metadata.create_all(bind=engine)` at `main.py:48`. SQLite already has the `tasks` table populated in production. Cannot drop and recreate.

**Decision:** Generate baseline migration from current `models.py`, then `alembic stamp head` on existing DBs.

**Procedure:**
1. `alembic init app/infrastructure/database/migrations` — creates `alembic.ini`, `env.py`, `versions/`.
2. Configure `env.py`:
   - `target_metadata = Base.metadata` (import from `app.infrastructure.database.models`).
   - `sqlalchemy.url` from `Config` (env var, not hardcoded).
   - `render_as_batch=True` in `context.configure(...)` for SQLite ALTER support.
3. Create baseline migration (capturing current schema):
   ```bash
   alembic revision --autogenerate -m "baseline_v1.1_schema"
   ```
   Inspect, ensure it matches existing `tasks` table. Edit if autogen drifts.
4. **Existing prod DBs:** run `alembic stamp head` once — marks baseline as applied without running it. New tables come in subsequent migrations.
5. **Fresh DBs:** run `alembic upgrade head`. Baseline migration creates `tasks` from scratch.
6. **Remove `Base.metadata.create_all()` from `main.py:48`** AFTER baseline is stamped on dev/prod. Replace with no-op or with `alembic upgrade head` invocation in lifespan startup (recommend: separate ops step, not auto-run, to avoid surprise schema changes on container restart).
7. v1.2 schema additions become migration `0002_add_users_and_keys.py`, `0003_add_user_id_to_tasks_nullable.py`, `0004_backfill_user_id`, `0005_make_user_id_not_null.py`.

**Why split user_id into 3 migrations:** zero-downtime — code that reads/writes `user_id` ships AFTER migration 0003 (column exists, nullable). Backfill (0004) is a data migration. NOT NULL constraint (0005) ships AFTER all writers set user_id.

**SQLite + Alembic batch-ops:** SQLite cannot `ALTER COLUMN`. Alembic's `batch_alter_table` rebuilds the table. Batch mode is **mandatory** for any column-level alter on SQLite.

**File changes:**
- NEW `alembic.ini` at repo root.
- NEW `app/infrastructure/database/migrations/env.py` and `versions/`.
- DELETE `Base.metadata.create_all(bind=engine)` at `app/main.py:48` (after baseline stamped).
- MODIFY `pyproject.toml` / `requirements.txt` — add `alembic`.

---

## 7. CSRF Integration

**Decision:** **Dependency-based** (`Depends(verify_csrf)`), not middleware. Double-submit cookie pattern.

**Why dependency over middleware:**
- Bearer-auth routes must skip CSRF (no cookie = no CSRF surface). Middleware would need to reach into `request.state.auth_method` after auth middleware ran — works, but couples middlewares.
- Some session-auth routes are **read-only** (GET) and don't need CSRF. Dependency-based opt-in is explicit.
- FastAPI dependency tree is the natural place to express "this route requires CSRF".

**Pattern (double-submit):**
- On login (and on `GET /api/auth/csrf` for SPA bootstrap), server:
  - Sets `Set-Cookie: session=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/`
  - Sets `Set-Cookie: csrf=<random32>; Secure; SameSite=Lax; Path=/` (NOT HttpOnly — JS reads it)
- Frontend `apiClient` reads `csrf` cookie, attaches as `X-CSRF-Token` header on every state-mutating request.
- `verify_csrf` dependency: compare header to cookie via `secrets.compare_digest`.

**Exempt list:**
- All `Authorization: Bearer ...` requests (dependency early-returns when `auth_method == "bearer"`).
- Public/login/register routes (no session yet to forge).
- WebSocket — already same-origin enforced; cookie auto-sent; no separate CSRF needed for WS handshake (browser doesn't expose cross-origin WS to JS without CORS preflight on `connect`).

**Why double-submit not synchronizer-token:** stateless, no server-side store, perfect for SQLite-backed app where every read is a query.

**File changes:**
- NEW `app/services/csrf_service.py` (or fold into auth helpers).
- MODIFY `app/api/dependencies.py` — `verify_csrf` dep (shown above).
- MODIFY `app/api/{task,audio,tus_upload,streaming_upload,keys,account,auth}_api.py` — POST/PUT/PATCH/DELETE routes get `Depends(verify_csrf)` (one extra line).

---

## 8. Rate Limit Storage

**Decision:** **Token bucket in SQLite**, single dedicated table `rate_limit_buckets`. WAL already on. Token consumption inside same transaction as the request's session, atomic via `SELECT ... FOR UPDATE` (SQLite uses BEGIN IMMEDIATE).

**Why SQLite over in-memory:**
- In-memory dict = per-process. Fine for current `--workers 1` deploy. Breaks the moment ops scales workers (no warning, silently allows N× the limit).
- Free tier limits (5 req/hr) are user-facing contract. Cannot rely on "we only run one worker forever".
- Worker-safe by construction.

**Why SQLite over Redis:**
- Project explicitly avoids new infra deps (single container constraint).
- Rate limit writes are low-volume (request/s, not message/s). SQLite WAL handles this trivially.
- One less moving part for ops.

**Schema:**
```python
class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str]                        # "user:<id>", "ip:<cidr>", "register:<cidr>"
    bucket_key: Mapped[str]                   # "transcribe", "register", "login"
    tokens_remaining: Mapped[float]           # float = supports refill at fractional rate
    last_refill_at: Mapped[datetime]
    capacity: Mapped[int]                     # plan-tier-specific
    refill_per_second: Mapped[float]
    __table_args__ = (UniqueConstraint("scope", "bucket_key"),)
```

**Algorithm (in `RateLimitService.consume`):**
```
BEGIN IMMEDIATE;
SELECT * FROM rate_limit_buckets WHERE scope=? AND bucket_key=?;
elapsed = now - last_refill_at
new_tokens = min(capacity, tokens_remaining + elapsed * refill_per_second)
if new_tokens < 1:
    ROLLBACK; raise RateLimitExceeded(retry_after=...)
UPDATE ... SET tokens_remaining = new_tokens - 1, last_refill_at = now WHERE id = ?;
COMMIT;
```

`BEGIN IMMEDIATE` acquires a write lock immediately (vs deferred), serializing concurrent consume() calls per-user. Worker-safe even with multiple workers.

**IP rate limits** (register 3/hr per /24, login 10/hr per /24): same table, scope = `ip:<cidr-24>`. CIDR computed in middleware/dep using `ipaddress.ip_network("<ip>/24", strict=False)`.

**File changes:**
- MODIFY `app/infrastructure/database/models.py` — `RateLimitBucket`.
- NEW `app/services/rate_limit_service.py`.
- NEW `app/infrastructure/database/repositories/sqlalchemy_rate_limit_repository.py`.
- MODIFY `app/api/dependencies.py` — `rate_limit_dep` factory (per-route, configurable bucket key).
- MODIFY routes — `Depends(rate_limit_dep("transcribe"))` on heavy endpoints.

---

## 9. Frontend Route Structure

**Decision:** `react-router-dom@7` with `BrowserRouter` mounted at `/ui`. Auth context via `Zustand` (or React Context — pick Context for simplicity, no new dep). Redirect-on-401 inside the central `apiClient`.

**Structure:**
```
frontend/src/
  main.tsx                          # BrowserRouter basename="/ui"
  App.tsx                           # <Routes> declaration only
  routes/
    LoginPage.tsx                   # /ui/login
    RegisterPage.tsx                # /ui/register
    TranscribePage.tsx              # /ui/  (current upload UI moved here)
    DashboardLayout.tsx             # /ui/dashboard  (outlet + sidebar)
    DashboardKeysPage.tsx           # /ui/dashboard/keys
    DashboardUsagePage.tsx          # /ui/dashboard/usage
    DashboardAccountPage.tsx        # /ui/dashboard/account  (DELETE data lives here)
  components/
    auth/
      ProtectedRoute.tsx            # wrapper redirects to /login on no user
      AuthProvider.tsx              # context + useAuth hook
  lib/
    apiClient.ts                    # NEW — central fetch wrapper
    auth/
      authApi.ts                    # NEW — register/login/logout/me
      keyApi.ts                     # NEW — list/create/revoke
```

**`AuthProvider` responsibilities:**
- On mount: `apiClient.get('/api/auth/me')` → set user or null.
- Expose: `user`, `login(email, pw)`, `logout()`, `register(email, pw)`.
- Listen for `apiClient` 401 events → clear user, navigate to `/login`.

**`ProtectedRoute`:**
```tsx
export function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <Outlet />;
}
```

**App.tsx after refactor:**
```tsx
<AuthProvider>
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route element={<ProtectedRoute />}>
      <Route path="/" element={<TranscribePage />} />
      <Route path="/dashboard" element={<DashboardLayout />}>
        <Route path="keys" element={<DashboardKeysPage />} />
        <Route path="usage" element={<DashboardUsagePage />} />
        <Route path="account" element={<DashboardAccountPage />} />
      </Route>
    </Route>
  </Routes>
</AuthProvider>
```

**Existing `App.tsx` content** (UploadDropzone + FileQueueList + useUploadOrchestration) moves verbatim into `routes/TranscribePage.tsx`. No logic change.

**File changes:**
- MODIFY `frontend/src/App.tsx` — becomes routes shell.
- MODIFY `frontend/src/main.tsx` — wrap with `BrowserRouter basename="/ui"`.
- NEW `frontend/src/routes/*` (6 files).
- NEW `frontend/src/components/auth/{AuthProvider,ProtectedRoute}.tsx`.
- NEW `frontend/src/lib/apiClient.ts`.
- NEW `frontend/src/lib/auth/{authApi,keyApi}.ts`.

---

## 10. API Client Wrapper

**Decision:** Single `apiClient.ts` — thin wrapper around `fetch`. Owns CSRF header injection, 401 interception, and base URL. Existing `taskApi.ts`/`transcriptionApi.ts` route through it.

**Why central wrapper:**
- Today every file does its own `fetch`, its own error parsing, its own response shape conversion. DRY violation.
- Auth + CSRF + 401-redirect logic must be in ONE place. Otherwise drift — one file forgets the header, one route gets stuck in a redirect loop.

**Shape:**
```ts
// frontend/src/lib/apiClient.ts
type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;          // auto-JSON-stringified unless FormData
  skipCsrf?: boolean;      // for read-only or login routes
};

let on401: () => void = () => {};
export function setOn401Handler(fn: () => void) { on401 = fn; }

function getCsrfCookie(): string | null {
  return document.cookie.split("; ")
    .find((c) => c.startsWith("csrf="))?.slice(5) ?? null;
}

export async function apiFetch<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<ApiResult<T>> {
  const headers = new Headers(opts.headers);
  if (!opts.skipCsrf && opts.method && opts.method !== "GET") {
    const csrf = getCsrfCookie();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const isJson = opts.body !== undefined && !(opts.body instanceof FormData);
  if (isJson) headers.set("Content-Type", "application/json");

  const res = await fetch(path, {
    ...opts,
    headers,
    body: isJson ? JSON.stringify(opts.body) : (opts.body as BodyInit),
    credentials: "same-origin",   // cookie attached
  });

  if (res.status === 401) {
    on401();                        // AuthProvider clears user + navigates
    return { success: false, error: { status: 401, detail: "Unauthorized" } };
  }
  // ... existing ApiResult conversion (lifted from taskApi.ts)
}
```

**Integration with existing modules:**
- `taskApi.ts:21` `fetch('/task/${taskId}')` → `apiFetch('/task/${taskId}')`. Same return type.
- `transcriptionApi.ts:43` `fetch('/speech-to-text?...', { method: 'POST', body: formData })` → `apiFetch('/speech-to-text?...', { method: 'POST', body: formData })`. Body is FormData → wrapper sets CSRF, skips JSON.
- `tusUpload.ts` — tus-js-client owns its own XHR. Inject CSRF + cookie via `headers` option:
  ```ts
  new tus.Upload(file, {
    endpoint: TUS_ENDPOINT,
    headers: { "X-CSRF-Token": getCsrfCookie() ?? "" },
    withCredentials: true,
    ...
  });
  ```
  Bearer-auth API users supply `Authorization` instead via a different code path (out of scope for browser SPA).
- `useTaskProgress.ts` (WebSocket) — same-origin cookie auto-attached. No code change for browser. External clients pass subprotocol.

**`AuthProvider` wires the 401 handler on mount:**
```tsx
useEffect(() => {
  setOn401Handler(() => {
    setUser(null);
    navigate("/login", { replace: true });
  });
}, [navigate]);
```

**File changes:**
- NEW `frontend/src/lib/apiClient.ts`.
- MODIFY `frontend/src/lib/api/taskApi.ts` — replace `fetch` with `apiFetch`. Keep public signature.
- MODIFY `frontend/src/lib/api/transcriptionApi.ts` — same.
- MODIFY `frontend/src/lib/upload/tusUpload.ts` — accept optional `headers` extension; inject CSRF in the factory caller (`useTusUpload.ts`).
- MODIFY `frontend/src/hooks/useTaskProgress.ts` — no change for cookie auth; accept optional bearer for non-browser future.

---

## 11. Build Order — Justified

**Phase split (suggested for roadmap):**

| # | Phase | Ship Together? | Reason |
|---|-------|----------------|--------|
| **1** | Alembic baseline + DB schema for users/keys/billing/rate-limit | Standalone | Schema only. `tasks.user_id` NULLABLE. Zero behavior change. |
| **2** | Domain entities + repositories + DI providers | Standalone | Code added, not yet wired into any route. Zero behavior change. |
| **3** | Auth services (AuthService, KeyService, PasswordService, JwtTokenService, RateLimitService, CsrfService) | Standalone | Pure logic. Unit-testable. Not yet HTTP-exposed. |
| **4** | Admin CLI + backfill | Before Phase 5 | Must seed admin user + backfill orphan tasks BEFORE auth gate goes live, else first user request 401s. |
| **5** | DualAuthMiddleware + auth/account/keys routes + per-user task scoping + WebSocket auth + CSRF | **Atomic** | This is THE cutover. If you ship middleware without routes, login is impossible. If you ship routes without middleware, all requests still pass through old single-token middleware. If you skip task scoping, users see each other's tasks for one deploy window. **One deploy.** |
| **6** | Frontend router shell + AuthProvider + apiClient + auth pages + dashboard | **Atomic with Phase 5** | Once backend requires auth, the existing SPA breaks (no headers, no login UI). Must ship together as a single user-visible release. |
| **7** | Stripe schema stub + Subscription/UsageEvent models exposed in dashboard | Post-cutover | No external integration; placeholder. Safe to ship after cutover stabilizes. |
| **8** | Frontend test infra (Vitest + RTL + MSW) | Anytime / parallel | Independent of backend. |

**Why phases 5+6 must be atomic:**
- Backend cutover replaces middleware. The moment it deploys, SPA's raw `fetch('/task/...')` returns 401 in browser → blank UI.
- Cannot deploy backend cutover behind a feature flag easily — middleware runs on every request, including SPA shell load.
- Solution: build phases 1-4 as deploys 1-4 (silent). Then build the cutover (5+6) on a branch, test end-to-end against staging, deploy as one release.

**Why Phase 4 (admin CLI) before Phase 5:**
- New schema has FK `tasks.user_id`. Cutover ships `NOT NULL` constraint. Existing rows MUST have an owner before the constraint applies.
- Admin user is needed for first login post-cutover (no public registration testing yet — registration ships in cutover).

**Sequencing within Phase 5** (sub-phases for planning):
- 5a. Replace middleware in dev with feature flag (env `AUTH_V2_ENABLED=false` keeps old behavior). All wiring lands.
- 5b. Run migration `0005_make_user_id_not_null` after backfill confirmed.
- 5c. Flip flag in staging, full e2e test.
- 5d. Flip in prod with frontend release.

---

## Anti-Patterns to Avoid

### Two stacked auth middlewares
**What:** Separate `BearerAuthMiddleware` + `SessionAuthMiddleware`.
**Why bad:** Each must check public paths, OPTIONS, set state. Double work, double bug surface, ordering bugs.
**Instead:** One `DualAuthMiddleware` with two resolution paths.

### Filtering by user_id in the API layer
**What:** Endpoints do `tasks = repo.get_all(); return [t for t in tasks if t.user_id == user.id]`.
**Why bad:** Loads other users' rows into memory. Privacy bug if filter forgotten. Performance bug at scale.
**Instead:** `repo.set_user_scope(user.id)` — filter pushed to SQL `WHERE`.

### Token in WebSocket query string
**What:** `ws://host/ws/tasks/abc?token=whsk_xxx`.
**Why bad:** Tokens in URLs leak via proxy logs, browser history, server access logs.
**Instead:** `Sec-WebSocket-Protocol: whisperx.bearer.<token>`.

### `Base.metadata.create_all()` after Alembic introduced
**What:** Leaving line `main.py:48` after Alembic baseline.
**Why bad:** `create_all` creates tables not in metadata's order vs FK chain. Silently diverges from migration history. Schema drifts between dev/prod.
**Instead:** Delete the line. Run `alembic upgrade head` as a deploy step.

### CSRF middleware for all routes
**What:** Global CSRF middleware that blocks every POST.
**Why bad:** Bearer-auth API clients don't have CSRF cookies. Will 403 every external API call.
**Instead:** `Depends(verify_csrf)` per route. Skip when `auth_method == "bearer"`.

### In-memory rate limit dict
**What:** `_buckets: dict[int, TokenBucket] = {}` at module scope.
**Why bad:** Per-process. Multi-worker = limits multiplied by worker count. Lost on restart.
**Instead:** SQLite-backed bucket with `BEGIN IMMEDIATE` for atomicity.

### Frontend fetch scattered across files
**What:** Each `*Api.ts` calls `fetch()` directly.
**Why bad:** CSRF header / 401 handler / base URL drift. One file forgets, redirect loop or bypassed auth.
**Instead:** `apiClient.apiFetch()` is the only `fetch` caller in app code.

---

## Scalability Considerations

| Concern | Today (1 user) | At 100 users | At 10K users |
|---------|----------------|--------------|--------------|
| SQLite writes | Fine, WAL | Fine, WAL handles ~1000 writes/s | Bottleneck — migrate to Postgres (out of v1.2 scope) |
| Rate limit table | n/a | Single row per user/bucket — small | Hot rows → consider Redis. Schema is identical, swap repo impl. |
| JWT verification | Trivial | Trivial — stateless | Trivial — stateless |
| Argon2 hashing on login | Negligible | ~100ms/login (intentional) — fine | Add login throttle, consider warming up |
| API key hash lookup | n/a | Index on `api_keys.token_hash` | Same — index hit, no scan |
| WebSocket connections | 1-2 | 100 concurrent | 10K concurrent → uvicorn worker model insufficient, but not a v1.2 concern |
| Task scoping query plan | n/a | Index on `tasks.user_id` mandatory | Composite index `(user_id, created_at DESC)` |

---

## Sources

- Existing codebase grep verified (HIGH confidence on all integration-point file paths).
- FastAPI WebSocket Depends pattern — documented FastAPI feature since 0.65, verified via Context7 library resolve.
- Alembic SQLite batch_alter_table pattern — Alembic docs (HIGH confidence, standard advice).
- Argon2 password hashing — OWASP Password Storage Cheat Sheet (HIGH).
- Token bucket atomicity in SQLite — `BEGIN IMMEDIATE` documented in SQLite docs (HIGH).
- Double-submit CSRF — OWASP CSRF Cheat Sheet (HIGH).
- `Sec-WebSocket-Protocol` for token transport — RFC 6455 §4.2.2; common pattern in production WebSocket auth (MEDIUM-HIGH; verified in major libs).
