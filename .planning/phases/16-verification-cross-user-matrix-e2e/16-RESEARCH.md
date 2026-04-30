# Phase 16: Verification + Cross-User Matrix + E2E - Research

**Researched:** 2026-04-29
**Domain:** Test-only milestone gate — security invariants, JWT hardening, CSRF, WS tickets, migration smoke
**Confidence:** HIGH (all primary sources verified in repo; PyJWT 2.x + alembic 1.13+ behavior cited from training, cross-checked against existing test patterns in repo)

## Summary

Phase 16 ships ZERO runtime code. Five new pytest integration files prove every v1.2 security invariant. Strategy locked by 16-CONTEXT.md: parametrized cross-user matrix per endpoint, deterministic JWT forgery via direct base64 construction (bypassing PyJWT's algorithm safeguards on the encode path), double-submit CSRF mismatch tests over real `auth_full_app` fixture, mocked-clock WS ticket expiry, and `subprocess` alembic invocation against tmp_path SQLite (Phase 10 pattern).

All five tests reuse three already-proven slim-FastAPI fixture patterns from `test_account_routes.py`, `test_auth_routes.py`, and `test_ws_ticket_flow.py`. The repository already has a near-complete skeleton: `test_phase13_e2e_smoke.py` (subprocess uvicorn), `test_alembic_migration.py` (subprocess alembic), `test_ws_ticket_flow.py` (mocked datetime for expiry). Phase 16 work is composition, not invention.

**Primary recommendation:** Build a single shared `tests/integration/_phase16_helpers.py` module exporting `_seed_two_users()`, `_endpoint_catalog`, `_forge_jwt(alg)`, `_issue_csrf_pair()`, `WS_POLICY_VIOLATION` — five test files DRY-import. Use `auth_full_app`-style fixture (auth_router + DualAuthMiddleware + CsrfMiddleware + every Phase-13 router) as the single fixture for cross-user, JWT, and CSRF suites; reuse `ws_app` shape from `test_ws_ticket_flow.py` for VERIFY-07; reuse `_run_alembic` subprocess helper from `test_alembic_migration.py` for VERIFY-08.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Test File Layout:**
- `tests/integration/test_security_matrix.py` — VERIFY-01 cross-user matrix (parametrized table)
- `tests/integration/test_jwt_attacks.py` — VERIFY-02, VERIFY-03, VERIFY-04
- `tests/integration/test_csrf_enforcement.py` — VERIFY-06
- `tests/integration/test_ws_ticket_safety.py` — VERIFY-07
- `tests/integration/test_migration_smoke.py` — VERIFY-08

**Cross-User Matrix Strategy:**
- pytest parametrize over endpoint × {self, foreign} → expected status assertions
- Two TestClient instances, separate cookie jars, same app + DB
- Endpoint catalog hardcoded as module-level constant (DRY single source)
- Every endpoint must produce the same opaque 404 body for unknown-id and foreign-id (anti-enumeration parity already proven in Plan 13-07; this phase verifies it)

**JWT Attack Strategy:**
- Forge tokens by direct `header64.payload64.signature64` construction (bypass library validation)
- alg=none token: header={"alg":"none","typ":"JWT"}, payload=valid sub, signature=""
- Tampered: take valid token, flip last char of signature
- Expired: issue with iat=now-86400, exp=now-3600 (must use real signing key but past expiry)
- Each test sends token via Authorization: Bearer header AND via session cookie — both paths must 401

**CSRF Strategy:**
- Use existing TestClient session login flow → captures both `session` + `csrf_token` cookies
- 3 test cases per state-mutating endpoint: missing X-CSRF-Token, mismatched X-CSRF-Token, matching X-CSRF-Token
- Bearer auth (API key) tests: confirm CSRF check skipped (header absent → still succeeds)

**WS Ticket Strategy:**
- Mock `time.monotonic` for expired-ticket test (>60s without sleeping in real time)
- Direct in-memory ticket store inspection — Phase 13 used dict + threading.Lock; tests can introspect via the singleton
- Cross-user ticket: issue ticket for User A's task, attempt to consume with User B's connection identity → 1008 close

**Migration Smoke Strategy:**
- Use a snapshot SQLite file in `tests/fixtures/migration/records-v1.1.db` if present, else build a synthetic baseline schema in-test
- Copy to `tmp_path` so test is isolated
- Run `subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env={DB_URL: tmp_db})` — venv-portable per Plan 10-04 lesson
- Assertions: tasks.user_id IS NOT NULL for all rows, foreign keys enforce, row count preserved, admin user seeded

**Code Quality Invariants:**
- DRY: shared `_seed_two_users(session)` fixture; single `_endpoint_catalog` constant; reuse Phase 15 `_seed_full_user_universe` if applicable
- SRP: one test file per VERIFY cluster
- Tiger-style: assertions at boundaries; explicit error-message asserts (not just status codes)
- No nested-if (verifier grep returns 0 across new test files)
- Self-explanatory names: `tampered_token` not `t`, `foreign_user_client` not `c2`

### Claude's Discretion

- Exact pytest fixture composition (use existing `tests/conftest.py` patterns)
- Choice of how to forge alg=none tokens (urlsafe_b64encode of JSON works)
- Whether migration smoke uses `subprocess.run` or `alembic.command.upgrade` API directly — pick whichever produces fewer flaky cases on Windows

### Deferred Ideas (OUT OF SCOPE)

- Real load test / fuzzing — not in v1.2
- Cypress / Playwright cross-user matrix — Phase 15 e2e suite covers UI; backend matrix suffices
- Dependency pin audit — out of scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VERIFY-01 | Cross-user matrix proves user A's tasks/keys/usage never visible to user B for any endpoint | §1 endpoint catalog + §6 fixture-reuse table |
| VERIFY-02 | JWT alg=none token rejected with 401 | §2 forging technique (alg=none branch) |
| VERIFY-03 | Tampered JWT signature rejected with 401 | §2 forging technique (tamper branch) |
| VERIFY-04 | Expired JWT rejected with 401 | §2 forging technique (expired branch) |
| VERIFY-06 | CSRF token mismatch returns 403 | §3 CSRF test fixtures |
| VERIFY-07 | WS ticket flow rejects re-use, expired tickets, and tickets bound to other users | §4 WS ticket test mechanics |
| VERIFY-08 | Migration smoke against records.db copy: baseline → upgrade → verify ownership backfill | §5 alembic migration smoke pattern |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- DRT (Do Not Repeat Yourself) — shared helpers in `tests/integration/_phase16_helpers.py`
- SRP — one test file per VERIFY cluster
- Caveman mode for all assistant responses — does NOT affect test code (test code follows project Python style)

[VERIFIED: ./CLAUDE.md, $HOME/.claude/CLAUDE.md, MEMORY.md feedback_code_quality.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cross-user isolation enforcement | API / Backend | Database (FK + scoped queries) | DualAuthMiddleware + scoped repositories already enforce; tests verify externally via HTTP |
| JWT validation | API / Backend | — | Single decode site `app/core/jwt_codec.py`; tests probe via HTTP only |
| CSRF enforcement | API / Backend (CsrfMiddleware) | — | Stateless middleware; tests probe via HTTP only |
| WS ticket lifecycle | API / Backend (WsTicketService) | — | In-memory dict + lock; tests probe via WS handshake |
| Schema migration | Database / Storage | — | Alembic; tests run subprocess against tmp SQLite file |
| Test orchestration | Test harness (pytest) | — | All tests are pytest integration tests with `@pytest.mark.integration` marker |

[VERIFIED: app/main.py middleware stack, app/core/dual_auth.py, app/core/csrf_middleware.py, app/services/ws_ticket_service.py, alembic/versions/]

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | Test runner with strict markers | [VERIFIED: pyproject.toml dev deps] — already used by every existing integration test |
| starlette TestClient (via fastapi.testclient) | bundled with fastapi 0.128.0 | HTTP + WS in-process testing | [VERIFIED: pyproject.toml] — used in test_account_routes.py, test_auth_routes.py, test_ws_ticket_flow.py |
| sqlalchemy | bundled | DB introspection in assertions | [VERIFIED: existing tests use `text()` + `session.execute()`] |
| dependency-injector | >=4.41.0 | Container override per test | [VERIFIED: pyproject.toml; existing fixtures use `providers.Factory(session_factory)`] |
| pyjwt | >=2.8.0 | Real session-token signing for the expired-token test | [VERIFIED: pyproject.toml; PyJWT 2.x rejects `alg=none` on decode by default] [CITED: PyJWT docs — `algorithms=["HS256"]` parameter on decode is mandatory] |
| alembic | >=1.13.0 | Migration smoke subprocess | [VERIFIED: pyproject.toml + existing test_alembic_migration.py uses `subprocess.run([sys.executable, "-m", "alembic", ...])`] |
| httpx | 0.28.1 | Subprocess-mode E2E (not needed in Phase 16 — TestClient sufficient) | [VERIFIED: pyproject.toml; only used in test_phase13_e2e_smoke.py] |

### Supporting (already wired — DRY reuse)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dependency_injector.providers.Factory | 4.41+ | Per-test session-factory override | All 5 new tests — copy pattern from `test_account_routes.py:91-110` |
| slowapi.errors.RateLimitExceeded | 0.1.9+ | Required exception handler in slim-app fixtures | Mounted via `app.add_exception_handler(RateLimitExceeded, rate_limit_handler)` AND `app.state.limiter = limiter` AND `limiter.reset()` in fixture setup AND teardown |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `subprocess.run([..., "alembic", ...])` (Phase 10 pattern) | `alembic.config.Config()` + `alembic.command.upgrade(cfg, "head")` direct API | In-process API binds to current `app.infrastructure.database.engine` (module-load), so the test would need to monkey-patch `DB_URL` BEFORE alembic imports. Subprocess gets clean env. **Decision: subprocess wins on Windows, mirrors test_alembic_migration.py + test_phase13_e2e_smoke.py — same lesson learned in Plan 10-04.** [VERIFIED: tests/integration/test_alembic_migration.py:34-53] |
| Mocking `datetime.now` via `monkeypatch.setattr("app.services.ws_ticket_service.datetime", ...)` (existing test_ws_ticket_flow.py pattern) | Mocking `time.monotonic` (CONTEXT.md mention) | `WsTicketService.consume` uses `datetime.now(timezone.utc)`, NOT `time.monotonic`. **Decision: stick with the proven `_FrozenDatetime` subclass pattern from `test_ws_ticket_flow.py:295-322`. CONTEXT.md mention of `time.monotonic` is a doc-level hint, not the actual implementation.** [VERIFIED: app/services/ws_ticket_service.py:112 uses `datetime.now`] |
| Subprocess uvicorn (test_phase13_e2e_smoke.py pattern) | TestClient (existing slim-app fixtures) | Subprocess pays ~5-10s boot per test. **Decision: TestClient for all 5 files. Subprocess only adds value when testing module-load behavior or feature-flag flips — Phase 16 doesn't.** Migration smoke is `_run_alembic` subprocess (small, fast); it does NOT need uvicorn. |

**Installation:**
No new dependencies. All required libraries already in `pyproject.toml` (verified above).

**Version verification:** All versions cited from pyproject.toml current text. No new pin required.

## Architecture Patterns

### System Architecture Diagram

```
                       ┌──────────────────────────────────────────────┐
                       │   pytest tests/integration/test_*.py         │
                       └──────────────────────────────────────────────┘
                                          │
                                          ▼
                       ┌──────────────────────────────────────────────┐
                       │   Fixture: per-test slim FastAPI app         │
                       │   ─ auth_router + key_router + task_router   │
                       │   ─ ws_ticket_router + websocket_router      │
                       │   ─ account_router + billing_router          │
                       │   ─ DualAuthMiddleware + CsrfMiddleware      │
                       │   ─ Container.db_session_factory.override()  │
                       │   ─ tmp_path SQLite (Base.metadata.create_all)│
                       └──────────────────────────────────────────────┘
                                          │
                       ┌──────────────────┼───────────────────────────┐
                       ▼                  ▼                           ▼
            ┌─────────────────┐  ┌─────────────────┐    ┌──────────────────────┐
            │ TestClient A    │  │ TestClient B    │    │ subprocess alembic   │
            │ (User A jar)    │  │ (User B jar)    │    │ (VERIFY-08 only)     │
            └─────────────────┘  └─────────────────┘    └──────────────────────┘
                       │                  │                           │
                       └─────┬────────────┘                           │
                             ▼                                        ▼
                ┌───────────────────────────┐         ┌──────────────────────────┐
                │  HTTP/WS request          │         │  alembic upgrade head    │
                │  ─ register / login       │         │  on tmp records.db copy  │
                │  ─ POST /api/keys         │         │  ↓                       │
                │  ─ GET /tasks             │         │  inspect tasks.user_id   │
                │  ─ DELETE /api/account    │         │  inspect FK enforcement  │
                │  ─ ws/tasks/{id}?ticket=  │         │  inspect row count       │
                └───────────────────────────┘         └──────────────────────────┘
                             │
                             ▼
                ┌───────────────────────────┐
                │  Status code + body       │
                │  matrix-asserted via      │
                │  pytest.parametrize       │
                └───────────────────────────┘
```

Data flow:
1. pytest invokes one of 5 test files
2. Fixture wires Container → tmp DB → mounts routers + middleware
3. Test seeds 2 users (or 1 + admin for migration smoke)
4. Two TestClient jars exercise endpoints with deliberately-forged or mismatched credentials
5. Asserts status code + body parity (anti-enumeration) + DB row state (cross-user isolation)

### Recommended Project Structure
```
tests/integration/
├── _phase16_helpers.py             # NEW — DRY shared helpers
├── test_security_matrix.py         # NEW — VERIFY-01
├── test_jwt_attacks.py             # NEW — VERIFY-02/03/04
├── test_csrf_enforcement.py        # NEW — VERIFY-06
├── test_ws_ticket_safety.py        # NEW — VERIFY-07
├── test_migration_smoke.py         # NEW — VERIFY-08
├── test_account_routes.py          # EXISTING — pattern source
├── test_auth_routes.py             # EXISTING — pattern source
├── test_ws_ticket_flow.py          # EXISTING — pattern source (subset of VERIFY-07)
├── test_phase13_e2e_smoke.py       # EXISTING — pattern source for subprocess if needed
└── test_alembic_migration.py       # EXISTING — pattern source for subprocess alembic

tests/fixtures/migration/           # NEW (optional — if a real records.db sample is provided)
└── records-v1.1.db                 # OPTIONAL snapshot; otherwise synthetic in-test
```

### Pattern 1: Slim FastAPI per-test fixture (DRY)
**What:** Wire one Container with overridden DB factory, mount only the routers under test, register `DualAuthMiddleware` + `CsrfMiddleware`, register exception handlers (`RateLimitExceeded`, `InvalidCredentialsError`, `ValidationError`).

**When to use:** test_security_matrix.py, test_jwt_attacks.py, test_csrf_enforcement.py.

**Example:** [VERIFIED: tests/integration/test_account_routes.py:88-117]
```python
@pytest.fixture
def app_full(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app — every Phase-13 router + dual-auth + CSRF middleware."""
    container = Container()
    container.db_session_factory.override(providers.Factory(session_factory))
    dependencies.set_container(container)

    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(TaskNotFoundError, _task_not_found_handler)
    app.include_router(auth_router)
    app.include_router(key_router)
    app.include_router(task_router)
    app.include_router(account_router)
    app.include_router(billing_router)
    app.include_router(ws_ticket_router)
    app.include_router(websocket_router)
    # ASGI middleware reverses registration order: register CSRF first → DualAuth runs first.
    app.add_middleware(CsrfMiddleware, container=container)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()
```

### Pattern 2: Two-client cross-user setup
**What:** Spawn two TestClient instances over the same FastAPI app — separate cookie jars per user.

**Example:** [VERIFIED: tests/integration/test_account_routes.py:313-345]
```python
client_a = TestClient(app)
client_b = TestClient(app)
user_a_id = _register(client_a, "alice@example.com")
user_b_id = _register(client_b, "bob@example.com")
# client_a's jar holds A's session+csrf_token; client_b's holds B's.
```

### Pattern 3: Direct base64 JWT forgery (no library)
**What:** Bypass PyJWT's `algorithms=` allow-list by hand-rolling `header.payload.signature` using `base64.urlsafe_b64encode` of `json.dumps(...)`. PyJWT 2.x refuses to encode `alg=none` unless explicitly allowed; constructing the bytes directly evades that guard so the server-side decode rejects it the same way a real attacker's would.

**When to use:** test_jwt_attacks.py (VERIFY-02 alg=none, VERIFY-03 tampered).

**Example:**
```python
import base64
import json

def _b64url(payload: dict | bytes) -> str:
    """JWT-spec base64url: URL-safe, no padding."""
    raw = payload if isinstance(payload, bytes) else json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def _forge_alg_none_token(*, user_id: int, token_version: int = 0) -> str:
    """Build header.payload.<empty signature> with alg=none (RFC 7519 §6.1)."""
    header = {"alg": "none", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + 86400,
        "ver": token_version,
        "method": "session",
    }
    return f"{_b64url(header)}.{_b64url(payload)}."  # trailing dot, empty signature
```

[CITED: RFC 7519 §6.1 (Plaintext JWS), PyJWT 2.x docs — `decode(..., algorithms=["HS256"])` rejects `alg=none` with `InvalidAlgorithmError`] [VERIFIED: app/core/jwt_codec.py:54 maps `InvalidAlgorithmError → JwtAlgorithmError`; DualAuthMiddleware catches both → returns `_unauthorized()` 401]

### Pattern 4: Tampered signature (mutate last char)
```python
def _tamper_jwt(token: str) -> str:
    """Flip the last char of the signature segment so HMAC verify fails."""
    head, payload, sig = token.split(".")
    flipped = "A" if sig[-1] != "A" else "B"
    return f"{head}.{payload}.{sig[:-1]}{flipped}"
```
PyJWT raises `InvalidSignatureError` (subclass of `InvalidTokenError`) → mapped to `JwtTamperedError` in `jwt_codec.decode_session` → DualAuthMiddleware returns 401.
[VERIFIED: app/core/jwt_codec.py:59-60]

### Pattern 5: Expired JWT (real signing, past exp)
```python
def _forge_expired_token(*, user_id: int, secret: str, token_version: int = 0) -> str:
    """Sign a real HS256 token with iat+exp in the past — server raises JwtExpiredError."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now - 86400,
        "exp": now - 3600,  # 1 hour past expiry
        "ver": token_version,
        "method": "session",
    }
    return jwt.encode(payload, secret, algorithm="HS256")
```
Server raises `ExpiredSignatureError` → mapped to `JwtExpiredError` → DualAuthMiddleware returns 401.
[VERIFIED: app/core/jwt_codec.py:55-56]

### Pattern 6: WS ticket time-warp (existing pattern reused)
[VERIFIED: tests/integration/test_ws_ticket_flow.py:294-328]
```python
class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return fake_now  # captured from outer scope

monkeypatch.setattr("app.services.ws_ticket_service.datetime", _FrozenDatetime)
```

### Pattern 7: Subprocess alembic (Phase 10 pattern reused)
[VERIFIED: tests/integration/test_alembic_migration.py:34-53]
```python
def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DB_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
```

### Anti-Patterns to Avoid
- **In-process `alembic.command.upgrade(cfg)` for migration smoke** — engine binds at module-load via `app.infrastructure.database.connection.engine`, so test would need to monkey-patch `DB_URL` before that import; subprocess gives clean env. [VERIFIED: app/core/config.py + app/infrastructure/database/connection.py module-load behavior]
- **Reusing one TestClient for both users** — cookie jar collision; tests pass but mask cross-user bugs. Always two clients.
- **Mocking `time.monotonic`** — `WsTicketService.consume` uses `datetime.now(timezone.utc)`, not `time.monotonic`. [VERIFIED: app/services/ws_ticket_service.py:112]
- **Asserting only status code without body parity** — anti-enumeration requires identical body bytes between unknown-id and foreign-id 404s. Test must `assert response.json() == {"detail": "Task not found"}` for BOTH legs.
- **`Base.metadata.create_all` in migration smoke test** — that bypasses alembic. Migration smoke MUST go through `subprocess alembic upgrade head` to verify the migrations themselves.
- **Forgetting `limiter.reset()` in fixture setup AND teardown** — slowapi 3/hr register limit accumulates across tests. [VERIFIED: every existing slim-app fixture resets twice]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Two-user setup | Custom user-creation helper | `_register(client, email)` already proven in 4 existing test files | DRY single source — copy verbatim into `_phase16_helpers.py` |
| Slim FastAPI fixture | Reinvent middleware/router stack per file | Reuse the `auth_full_app` shape from `test_auth_routes.py:127-159` | Already verified across 12+ tests |
| Subprocess alembic | Custom Process spawn | Reuse `_run_alembic` from `test_alembic_migration.py:34-53` | Identical Windows venv handling already proven |
| WS ticket time-warp | Sleep 60+ seconds | `_FrozenDatetime` monkeypatch [VERIFIED: test_ws_ticket_flow.py:295-322] | Sub-second test runs |
| JWT tamper detection | Mutate payload claims | Mutate last char of signature — pyJWT raises `InvalidSignatureError` regardless of payload | Cleaner test signal — payload mutation could pass JSON parse but fail HMAC anyway |
| Cross-user same-app two-client | Multi-process test setup | Two `TestClient(app)` instances — separate cookie jars | Already proven in `test_account_routes.py:319-321` |
| CSRF token capture | Re-implement double-submit | Capture cookies from `register` response: `response.cookies["csrf_token"]` | TestClient persists cookies in `client.cookies`; manipulate via `client.cookies.set("csrf_token", ...)` |

**Key insight:** Phase 16 invents nothing. Five existing test files already model every required pattern. New work is composing them into requirement-specific assertion clusters.

## Runtime State Inventory

> N/A — Phase 16 is test-only. No runtime state changes, no rename/refactor, no migrations to data. The migration smoke test (VERIFY-08) operates on a tmp_path COPY of records.db; the production records.db is untouched.

**Categories explicitly checked and confirmed empty:**
- Stored data — no production DB writes
- Live service config — no config changes
- OS-registered state — no service registrations
- Secrets/env vars — tests use `AUTH__JWT_SECRET=secrets.token_urlsafe(32)` per fixture (already pattern in test_phase13_e2e_smoke.py)
- Build artifacts — no new packages

## Common Pitfalls

### Pitfall 1: Slowapi limiter state leaks between tests
**What goes wrong:** `/auth/register` is rate-limited 3/hr per /24. After 3 registers in test N, test N+1 starts pre-throttled.

**Why it happens:** `limiter` is a singleton imported from `app.core.rate_limiter`; in-memory token bucket persists across pytest sessions in the same process.

**How to avoid:** Call `limiter.reset()` in fixture setup AND teardown. [VERIFIED: every existing slim-app fixture does this — `test_account_routes.py:97 + 111`, `test_auth_routes.py:96 + 110`]

**Warning signs:** Cross-user matrix test seeing 429 instead of expected 201 on register.

### Pitfall 2: TestClient cookie jar contamination
**What goes wrong:** Test registers User A, then registers User B, but cookies from A's response auto-attached to B's POST. CSRF mismatch surfaces as 403 instead of expected outcome.

**Why it happens:** `TestClient` inherits httpx cookie persistence — POSTs auto-send the jar's cookies.

**How to avoid:** `client.cookies.clear()` between user switches OR use two TestClient instances. [VERIFIED: pattern in test_phase13_e2e_smoke.py:_register helper at lines 195-219; test_ws_ticket_flow.py:213-216]

**Warning signs:** Test gets 403 (CSRF) where it expected 401 (auth) or 200/201 (success).

### Pitfall 3: ASGI middleware order reversed
**What goes wrong:** Register CSRF first, then DualAuth — but middleware reverses on dispatch, so DualAuth runs second. Result: `request.state.auth_method` not yet set when CsrfMiddleware reads it → bypasses CSRF unintentionally.

**Why it happens:** Starlette ASGI semantics: last-registered runs FIRST on request.

**How to avoid:** Register CSRF BEFORE DualAuth in fixture setup. [VERIFIED: app/main.py:200-203 — `add_middleware(Csrf)` then `add_middleware(DualAuth)` so request flow is `Cors → DualAuth → Csrf → route`]

**Warning signs:** CSRF test passes when it should fail (or fails in unexpected place).

### Pitfall 4: TestClient WS does NOT run middleware
**What goes wrong:** Test for WS ticket cross-user wires DualAuthMiddleware then opens `client.websocket_connect(...)` — but `BaseHTTPMiddleware` only dispatches HTTP scopes, not WS.

**Why it happens:** Documented in `app/core/dual_auth.py:20-23` and `app/api/websocket_api.py:69-72`.

**How to avoid:** WS endpoint reaches into `app.api.dependencies._container` directly. Test relies on container override (which we already do in fixture). DualAuthMiddleware not in the WS path is by design — ticket flow is the auth.

**Warning signs:** WS test fails because expected auth context missing — but consume() succeeds → user_id mismatches in handler.

### Pitfall 5: Migration test contaminates global engine
**What goes wrong:** Migration smoke runs `subprocess alembic upgrade head`, but in-process tests imported `app.infrastructure.database.engine` early — its URL is the session-scoped tmp DB from `tests/conftest.py`, not the one we're migrating.

**Why it happens:** `engine` binds at module-load.

**How to avoid:** subprocess gets its own env with `DB_URL=sqlite:///{tmp_path}/migrate.db`. The in-process engine is irrelevant — we never query it from the migration test. All assertions use a fresh `create_engine(f"sqlite:///{tmp_path}/migrate.db")` after subprocess exits. [VERIFIED: test_alembic_migration.py:56-61 uses `_make_engine` per assertion]

**Warning signs:** Migration test passes against the wrong DB.

### Pitfall 6: Forged JWT must include `ver` claim matching server
**What goes wrong:** Forge alg=none token with payload missing `ver` → DualAuthMiddleware decodes successfully, then `TokenService.verify_and_refresh` raises `KeyError("ver")` → 401 anyway, but test passes for the wrong reason (and a future bug fix to `verify_and_refresh` could regress this).

**Why it happens:** `app/core/dual_auth.py:182` catches `KeyError, ValueError` alongside the JWT exceptions → all collapse to 401.

**How to avoid:** Forged tokens MUST include `ver=user.token_version` (default 0 for newly-registered user). Test reads token_version from DB before forging.

**Warning signs:** Test passes but assertion uses `assert response.status_code == 401` without checking the rejection reason — flaky if future refactor splits handlers.

### Pitfall 7: alg=none header lower-case vs Title-case
**What goes wrong:** PyJWT compares `alg` case-sensitively; `"None"` vs `"none"`. Spec says lower-case. [CITED: RFC 7519 §4.1.1 + PyJWT source]

**How to avoid:** Use `"alg": "none"` (lower-case) — matches RFC and PyJWT's rejection logic.

### Pitfall 8: Migration smoke needs `users` admin row before `tasks` UNIQUE-FK validation
**What goes wrong:** VERIFY-08 wants `tasks.user_id IS NOT NULL` post-upgrade, but 0003 migration's pre-flight orphan-check raises RuntimeError if any tasks row has `user_id IS NULL`. Synthetic baseline schema must mirror v1.1 (no user_id col on tasks).

**Why it happens:** 0003_tasks_user_id_not_null.upgrade pre-flight `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL` → only meaningful AFTER 0002 added the col. So flow: build v1.1 tasks (no user_id) → stamp 0001_baseline → upgrade to 0002 (adds nullable user_id) → run backfill SQL inline → upgrade to 0003. OR simulate the backfill via direct UPDATE before running 0003.

**How to avoid:** Two valid sequences:
- **A**: Build legacy tasks → stamp 0001 → upgrade to 0002 (`alembic upgrade 0002_auth_schema`) → INSERT admin user → UPDATE tasks SET user_id=admin → upgrade to head → assert.
- **B**: Build legacy tasks → upgrade to head WITH backfill via `_run_alembic(["upgrade", "0002_auth_schema"])` mid-flow.

[VERIFIED: alembic/versions/0003_tasks_user_id_not_null.py:46-56 raises if orphans present; existing test_alembic_migration.py:test_brownfield_stamp_then_upgrade does upgrade head from a stamped 0001 with 0 task rows so the orphan check sees 0 and passes — Phase 16 needs the variant with seeded tasks to actually exercise the backfill assertion]

## Code Examples

Verified patterns from existing test files:

### CSRF mismatch test
```python
@pytest.mark.integration
def test_csrf_token_mismatch_returns_403(client: TestClient) -> None:
    """Cookie-auth POST with wrong X-CSRF-Token returns 403."""
    cookies = _register_and_capture(client, "csrf-mismatch@example.com")
    # csrf_token cookie is e.g. "abc123..." — header sends a DIFFERENT token
    response = client.post(
        "/api/keys",
        json={"name": "should-fail"},
        cookies=cookies,
        headers={"X-CSRF-Token": "deadbeef-mismatch-not-the-cookie-value"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token mismatch"
```
[VERIFIED: app/core/csrf_middleware.py:67-68 returns `_csrf_error("CSRF token mismatch")`]

### Cross-user matrix parametrization
```python
ENDPOINT_CATALOG: list[tuple[str, str, int]] = [
    # (method, path-template, expected_foreign_status)
    ("GET",    "/task/all",                       200),  # caller's empty set → 200 with []
    ("GET",    "/task/{task_id}",                 404),  # foreign task → opaque 404
    ("DELETE", "/task/{task_id}/delete",          404),  # foreign task → 404
    ("GET",    "/tasks/{task_id}/progress",       404),  # foreign task → 404
    ("POST",   "/api/ws/ticket",                  404),  # foreign task_id → opaque 404
    ("DELETE", "/api/keys/{key_id}",              404),  # foreign key → 404
    ("DELETE", "/api/account/data",               204),  # ALWAYS scoped to caller
    # ("DELETE", "/api/account",                  204),  # caller-only by design — covered by Phase 15 cross-user test
    ("GET",    "/api/account/me",                 200),  # caller-only by design
    # POST /speech-to-text* + TUS upload path do not have a "foreign-id" surface
    # (the caller can only POST their own files; cross-user comes via task_id later)
]

@pytest.mark.integration
@pytest.mark.parametrize("method,path_tmpl,expected_status", ENDPOINT_CATALOG)
def test_cross_user_endpoint(
    method: str, path_tmpl: str, expected_status: int,
    client_a: TestClient, client_b: TestClient,
    user_a_resources: dict,
) -> None:
    """User B accessing User A's resource id returns expected_status."""
    path = path_tmpl.format(**user_a_resources)
    if method == "POST":
        response = client_b.request(method, path, json={"task_id": user_a_resources["task_id"]}, headers={"X-CSRF-Token": client_b.cookies["csrf_token"]})
    elif method in {"DELETE", "PUT", "PATCH"}:
        response = client_b.request(method, path, headers={"X-CSRF-Token": client_b.cookies["csrf_token"]})
    else:
        response = client_b.request(method, path)
    assert response.status_code == expected_status, response.text
```

### WS ticket cross-user (CONTEXT.md §60)
```python
@pytest.mark.integration
def test_ws_ticket_cross_user_close_1008(
    client: TestClient, session_factory
) -> None:
    """Ticket issued for User A's task; User B's connection identity attempts consume."""
    # User A registers + creates task + gets ticket
    user_a_id = _register(client, "alice-ws-cross@example.com")
    task_a_uuid = _insert_task(session_factory, user_id=user_a_id)
    ticket_resp = client.post("/api/ws/ticket", json={"task_id": task_a_uuid})
    ticket = ticket_resp.json()["ticket"]
    # Switch to User B
    client.cookies.clear()
    _register(client, "bob-ws-cross@example.com")
    # Use A's ticket on the WS endpoint — handler.consume() returns user_id=A,
    # but task.user_id (in DB) is also A, so the in-handler check passes.
    # The cross-user attack vector is "B forges/steals A's ticket"; defence in
    # depth is that the ticket includes the user_id ─ test by mutating the
    # task.user_id post-issue to simulate drift (CONTEXT §60 W1 second-line).
    with session_factory() as session:
        # Drift: change task ownership so consumed_user_id != task.user_id
        session.execute(
            text("UPDATE tasks SET user_id = :new WHERE uuid = :uuid"),
            {"new": 9999, "uuid": task_a_uuid},
        )
        session.commit()
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/tasks/{task_a_uuid}?ticket={ticket}"):
            pass
    assert exc.value.code == WS_POLICY_VIOLATION
```
[VERIFIED: app/api/websocket_api.py:100-102 — defense-in-depth `consumed_user_id != task.user_id` check]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mix_stderr=False` on Click CliRunner | `result.stderr` / `result.stdout` independent attrs | Click 8.2+ | If we ever subprocess the CLI from a Phase 16 test, no `mix_stderr` kwarg |
| In-process alembic via `command.upgrade(cfg)` | `subprocess.run([sys.executable, "-m", "alembic", ...])` | Plan 10-04 Windows lesson | Migration smoke must use subprocess |
| Single TestClient cross-user | Two TestClient instances | Plan 13-04 lesson | All Phase 16 cross-user tests use two instances |

**Deprecated/outdated:**
- Manual cookie-attribute construction in tests — use `_register()` helper that captures `response.cookies` dict.
- `client.delete(url, json=...)` — httpx forbids body on DELETE. Use `client.request("DELETE", url, json=...)`. [VERIFIED: tests/integration/test_account_routes.py:433-437; STATE.md line 270]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PyJWT 2.x raises `InvalidAlgorithmError` (subclass of `InvalidTokenError`) when decode receives `alg=none` against `algorithms=["HS256"]` | Pattern 3 | LOW — any JWT-decode rejection still surfaces 401 via `JwtTamperedError` catch in DualAuthMiddleware. Already verified by existing `JwtAlgorithmError` import in `jwt_codec.py:16` |
| A2 | A real records-v1.1.db sample is NOT in `tests/fixtures/migration/` and tests must build synthetic | Migration smoke | LOW — synthetic schema mirrors `_build_tasks_table` from `test_alembic_migration.py:64-86`; if a real sample is later dropped in, swap one helper |
| A3 | DELETE endpoints with body work via `client.request("DELETE", url, json=...)` (not `client.delete(url, json=...)`) | Pitfall list | NONE — confirmed by Phase 15 lesson [VERIFIED: STATE.md line 270] |
| A4 | The Phase 13 endpoint catalog is stable for the next 30 days | Pattern 2 | LOW — Phase 17 is docs-only; no new task-touching endpoints planned |

## Open Questions (RESOLVED)

1. **Should migration smoke use the production `records.db` directly?**
   - What we know: CONTEXT.md §66 says "Use a snapshot SQLite file ... else build a synthetic baseline schema in-test"
   - What's unclear: Whether one is committed to `tests/fixtures/migration/`
   - **Resolution: build synthetic in-test (no committed sample exists). Pattern matches `test_alembic_migration.py:_build_tasks_table`. Add a TODO note in test docstring saying "swap to real sample when ops captures one" — keeps door open for Phase 17 docs.**

2. **Subprocess vs in-process alembic API?**
   - What we know: STATE.md confirms Phase 10-04 Windows lesson — subprocess is portable.
   - **Resolution: subprocess (`_run_alembic` helper from existing test_alembic_migration.py).**

3. **WS ticket time-warp: time.monotonic vs datetime.now?**
   - What we know: CONTEXT.md mentions `time.monotonic`; actual code uses `datetime.now`.
   - **Resolution: `_FrozenDatetime` monkeypatch (existing pattern from test_ws_ticket_flow.py:295-322). CONTEXT mention was a doc-level shorthand, not a binding directive.**

4. **Should every endpoint catalog row include the matching `self`-call expected status (200/204)?**
   - **Resolution: yes — parametrize over (endpoint, persona) where persona ∈ {self, foreign}, expected_status differs. Single source of truth for endpoint behavior; both legs assertion-covered.**

5. **Cross-user matrix for /api/keys uses `key_id`; for /tasks uses `task_uuid`. How to unify?**
   - **Resolution: pre-seed both kinds via fixture; pass dict of resource ids; format path templates with named placeholders.**

6. **CSRF tests for bearer-auth endpoints?**
   - **Resolution: per CONTEXT.md §57, ONE bearer-auth case per CSRF file confirms the bypass: send Authorization: Bearer header WITHOUT X-CSRF-Token header — must succeed (verifies bearer wins resolution → CSRF skipped). Already proven in test_phase13_e2e_smoke.py:test_bearer_auth_skips_csrf — Phase 16 mirrors with explicit assertion.**

7. **Number of test cases per VERIFY ID:**
   - **VERIFY-01: ≥9 endpoint × foreign + ≥9 endpoint × self = 18+ via parametrize**
   - **VERIFY-02: 2 (alg=none via Bearer header + alg=none via session cookie)**
   - **VERIFY-03: 2 (tampered via Bearer + tampered via session cookie)**
   - **VERIFY-04: 2 (expired via Bearer + expired via session cookie)**
   - **VERIFY-06: 4 (missing header, mismatched header, matching header, bearer-bypass)**
   - **VERIFY-07: 5 (reuse, expired, cross-user, missing, unknown — 4 already exist in test_ws_ticket_flow.py; new file owns the gold copy)**
   - **VERIFY-08: 4 (greenfield → head, brownfield with seeded tasks → head, FK enforcement post-upgrade, row-count preserved + tasks.user_id NOT NULL)**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | All 5 tests | ✓ | 9.0.2 | — |
| sqlalchemy | DB introspection | ✓ | bundled | — |
| dependency-injector | Container override | ✓ | >=4.41.0 | — |
| pyjwt | Real signing for expired-token test | ✓ | >=2.8.0 | — |
| alembic CLI | Migration smoke subprocess | ✓ | >=1.13.0 | — |
| Python sys.executable | subprocess invocation | ✓ | 3.11+ | — |
| sqlite3 (built-in) | tmp_path DB | ✓ | stdlib | — |
| WebSocket support in TestClient | VERIFY-07 | ✓ | starlette bundled with fastapi 0.128.0 | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 with strict markers |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/integration/test_security_matrix.py tests/integration/test_jwt_attacks.py tests/integration/test_csrf_enforcement.py tests/integration/test_ws_ticket_safety.py tests/integration/test_migration_smoke.py -v` |
| Full suite command | `pytest tests/integration/ -m integration -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VERIFY-01 | User B receives 404/403 on every task-touching endpoint accessing User A's resources | integration (parametrized) | `pytest tests/integration/test_security_matrix.py -v` | ❌ Wave 0 |
| VERIFY-01 | User A receives 200/204 on the same endpoints accessing own resources (positive control) | integration (parametrized self-leg) | `pytest tests/integration/test_security_matrix.py -k self -v` | ❌ Wave 0 |
| VERIFY-02 | alg=none JWT via session cookie → 401 | integration | `pytest tests/integration/test_jwt_attacks.py::test_alg_none_via_cookie_returns_401 -x` | ❌ Wave 0 |
| VERIFY-02 | alg=none JWT via Authorization header → 401 (bearer path uses key, not JWT — confirms separation) | integration | `pytest tests/integration/test_jwt_attacks.py::test_alg_none_via_bearer_returns_401 -x` | ❌ Wave 0 |
| VERIFY-03 | Tampered JWT signature via cookie → 401 | integration | `pytest tests/integration/test_jwt_attacks.py::test_tampered_signature_via_cookie_returns_401 -x` | ❌ Wave 0 |
| VERIFY-03 | Tampered JWT signature via bearer → 401 | integration | `pytest tests/integration/test_jwt_attacks.py::test_tampered_signature_via_bearer_returns_401 -x` | ❌ Wave 0 |
| VERIFY-04 | Expired JWT via cookie → 401 | integration | `pytest tests/integration/test_jwt_attacks.py::test_expired_via_cookie_returns_401 -x` | ❌ Wave 0 |
| VERIFY-04 | Expired JWT via bearer → 401 | integration | `pytest tests/integration/test_jwt_attacks.py::test_expired_via_bearer_returns_401 -x` | ❌ Wave 0 |
| VERIFY-06 | Cookie-auth POST without X-CSRF-Token → 403 | integration (parametrized over endpoints) | `pytest tests/integration/test_csrf_enforcement.py::test_missing_csrf_returns_403 -v` | ❌ Wave 0 |
| VERIFY-06 | Cookie-auth POST with mismatched X-CSRF-Token → 403 | integration | `pytest tests/integration/test_csrf_enforcement.py::test_mismatched_csrf_returns_403 -v` | ❌ Wave 0 |
| VERIFY-06 | Cookie-auth POST with matching X-CSRF-Token → 201/204 | integration (positive control) | `pytest tests/integration/test_csrf_enforcement.py::test_matching_csrf_succeeds -v` | ❌ Wave 0 |
| VERIFY-06 | Bearer-auth POST without X-CSRF-Token → 201/204 (bearer skips CSRF) | integration | `pytest tests/integration/test_csrf_enforcement.py::test_bearer_skips_csrf -v` | ❌ Wave 0 |
| VERIFY-07 | WS ticket reused → close 1008 | integration | `pytest tests/integration/test_ws_ticket_safety.py::test_reused_ticket_close_1008 -x` | ❌ Wave 0 (existing test_ws_ticket_flow.py covers but not in VERIFY namespace) |
| VERIFY-07 | WS ticket expired (>60s mocked) → close 1008 | integration | `pytest tests/integration/test_ws_ticket_safety.py::test_expired_ticket_close_1008 -x` | ❌ Wave 0 |
| VERIFY-07 | WS ticket cross-user (consumed_user_id != task.user_id) → close 1008 | integration | `pytest tests/integration/test_ws_ticket_safety.py::test_cross_user_ticket_close_1008 -x` | ❌ Wave 0 |
| VERIFY-08 | alembic upgrade head against tmp records.db copy preserves all tasks rows | integration (subprocess) | `pytest tests/integration/test_migration_smoke.py::test_upgrade_preserves_task_rows -x` | ❌ Wave 0 |
| VERIFY-08 | After upgrade, tasks.user_id IS NOT NULL on every row + admin seeded | integration (subprocess) | `pytest tests/integration/test_migration_smoke.py::test_upgrade_assigns_admin_user -x` | ❌ Wave 0 |
| VERIFY-08 | After upgrade, FK constraints enforce (delete admin user with cascade rows → all FK CASCADE/SET NULL behaviors fire) | integration (subprocess) | `pytest tests/integration/test_migration_smoke.py::test_fk_constraints_enforced -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/integration/test_<file>.py -v` (only the file under change — fast feedback)
- **Per wave merge:** `pytest tests/integration/test_security_matrix.py tests/integration/test_jwt_attacks.py tests/integration/test_csrf_enforcement.py tests/integration/test_ws_ticket_safety.py tests/integration/test_migration_smoke.py -v` (all 5 new files)
- **Phase gate:** `pytest tests/integration/ -m integration -v` full integration suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/integration/_phase16_helpers.py` — DRY helpers (`_seed_two_users`, `_endpoint_catalog`, `_forge_jwt`, `_issue_csrf_pair`, `_run_alembic`, `_register`, `_insert_task`, `WS_POLICY_VIOLATION`)
- [ ] `tests/integration/test_security_matrix.py` — covers VERIFY-01
- [ ] `tests/integration/test_jwt_attacks.py` — covers VERIFY-02/03/04
- [ ] `tests/integration/test_csrf_enforcement.py` — covers VERIFY-06
- [ ] `tests/integration/test_ws_ticket_safety.py` — covers VERIFY-07 (gold copy; supersedes scattered checks)
- [ ] `tests/integration/test_migration_smoke.py` — covers VERIFY-08
- [ ] (optional) `tests/fixtures/migration/records-v1.1.db` — sample snapshot if ops can produce one; otherwise synthetic in-test

*No new test framework needed. pytest 9.0.2 + slim FastAPI + TestClient + subprocess alembic — all proven in existing tests.*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | DualAuthMiddleware (cookie + bearer); test files cover JWT attacks (V2.1.1, V2.5.1, V2.5.2) |
| V3 Session Management | yes | JWT HS256 + token_version + sliding refresh; tests cover invalidation (V3.2.2, V3.3.4) |
| V4 Access Control | yes | Cross-user matrix (V4.2.1, V4.2.2 — anti-enumeration via opaque 404) |
| V5 Input Validation | partial | Forged JWT structure validates input rejection (V5.1.5) |
| V6 Cryptography | partial | Verifies HS256 algorithm enforcement (V6.2.1); secrets.compare_digest used by CsrfService (V6.2.5) |
| V13 API & Web Service | yes | CSRF double-submit (V13.2.3 — protect state changes from CSRF) |

### Known Threat Patterns for FastAPI + JWT + cookie + bearer stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JWT alg=none confusion attack | Spoofing | `jwt.decode(token, secret, algorithms=["HS256"])` — explicit allow-list (single decode site `app/core/jwt_codec.py:54`) |
| Tampered JWT signature replay | Tampering | HS256 HMAC verify by PyJWT raises InvalidSignatureError |
| Stale JWT after logout-all | Spoofing | token_version compare in TokenService.verify_and_refresh — bumped on logout-all |
| Expired JWT replay | Tampering | exp claim enforced by PyJWT |
| Cross-user resource enumeration via 403 vs 404 differential | Information Disclosure | Opaque 404 with byte-identical body `{"detail": "Task not found"}` for unknown-id and foreign-id |
| CSRF on cookie-auth state mutation | Tampering | Double-submit CSRF cookie + X-CSRF-Token header via secrets.compare_digest |
| WS ticket replay | Tampering / Spoofing | Single-use atomic consume under threading.Lock; ticket marked consumed=True on first use |
| WS ticket TTL exceeded | Spoofing | 60s expiration enforced by WsTicketService.consume |
| WS ticket cross-user (forged) | Spoofing | Defence-in-depth `consumed_user_id != task.user_id` check in handler |
| Migration data loss / FK violation | Tampering | Alembic migration pre-flight orphan-row check; tests verify post-upgrade row count + tasks.user_id NOT NULL |

[VERIFIED: app/core/jwt_codec.py, app/core/csrf.py, app/core/dual_auth.py, app/core/csrf_middleware.py, app/services/ws_ticket_service.py, app/api/websocket_api.py, alembic/versions/0003_tasks_user_id_not_null.py]

## Threat Model (meta — Phase 16 specific)

| ID | Threat | Mitigation |
|----|--------|------------|
| T-16-01 | Stale fixtures mask real regressions (e.g. previous test's session cookie auto-attaches → false positive on auth check) | `client.cookies.clear()` between user-switches; two-client pattern verified in test_account_routes.py |
| T-16-02 | Brittle wall-clock asserts on TTL expiry | `_FrozenDatetime` monkeypatch — sub-second deterministic; pattern verified in test_ws_ticket_flow.py |
| T-16-03 | Migration test contaminates global SQLAlchemy engine | Subprocess alembic gets isolated env; test never queries the in-process engine; assertions create their own fresh engine on the tmp DB |
| T-16-04 | Test passes for wrong reason — endpoint returns 404 because rate-limit fired, not because of cross-user check | Always `limiter.reset()` in fixture setup; assert exact body text, not just status code |
| T-16-05 | Forged JWT decode error catch is too broad — 401 fires from `KeyError("ver")` not `JwtAlgorithmError` | Tests assert response body `"Authentication required"` AND server log contains expected error class via `caplog` (optional defense-in-depth) |
| T-16-06 | Real regression discovered during Phase 16 → tempting to patch inline | CONTEXT decision locked: any regression filed as separate hot-fix phase, NOT patched inline (D-RES locked) |
| T-16-07 | CSRF "matching" positive-control test passes because middleware bypasses CSRF for non-state-mutating method | Always use POST/DELETE/PATCH/PUT (state-mutating) — never GET — for CSRF positive control |
| T-16-08 | WS time-warp affects unrelated tests via class monkeypatch | `monkeypatch.setattr` is function-scoped; `_FrozenDatetime` lives only during that test |

## Naming + DRY Surface

Shared module: `tests/integration/_phase16_helpers.py`

```python
"""Shared helpers for Phase 16 verification tests (DRT — single source of truth).

Imported by test_security_matrix.py / test_jwt_attacks.py /
test_csrf_enforcement.py / test_ws_ticket_safety.py / test_migration_smoke.py.
"""

from __future__ import annotations
import base64
import json
import os
import subprocess
import sys
import time
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import jwt
import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ---- Constants ----
WS_POLICY_VIOLATION = 1008
JWT_HS256 = "HS256"
JWT_ALG_NONE = "none"
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---- Endpoint catalog (single source of truth for VERIFY-01 + VERIFY-06) ----
# Schema: (method, path_template, expected_foreign_status, requires_csrf)
# Path placeholders: {task_uuid}, {key_id}, {user_email}
ENDPOINT_CATALOG: list[tuple[str, str, int, bool]] = [
    ("GET",    "/task/all",                       200, False),
    ("GET",    "/task/{task_uuid}",               404, False),
    ("DELETE", "/task/{task_uuid}/delete",        404, True),
    ("GET",    "/tasks/{task_uuid}/progress",     404, False),
    ("POST",   "/api/ws/ticket",                  404, True),
    ("DELETE", "/api/keys/{key_id}",              404, True),
    ("DELETE", "/api/account/data",               204, True),
    ("GET",    "/api/account/me",                 200, False),
    # Note: POST /speech-to-text* + TUS upload have no foreign-id surface
    # (caller can only POST own files); cross-user enforcement on those
    # paths is via task_id at WS subscription time, covered by /api/ws/ticket.
]


# ---- User seeding ----
def _register(client: TestClient, email: str, password: str = "supersecret123") -> int:
    """Register a user via /auth/register; return user_id (cookies seated on client)."""
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return int(response.json()["user_id"])


def _seed_two_users(
    client_a: TestClient, client_b: TestClient
) -> tuple[int, int]:
    """Register User A on client_a + User B on client_b (separate cookie jars)."""
    user_a = _register(client_a, "user-a@phase16.example.com")
    user_b = _register(client_b, "user-b@phase16.example.com")
    return user_a, user_b


def _insert_task(session_factory, *, user_id: int, file_name: str = "audio.mp3") -> str:
    """INSERT a task owned by user_id; return its UUID."""
    from app.infrastructure.database.models import Task as ORMTask
    with session_factory() as session:
        task_uuid = f"uuid-{user_id}-{datetime.now(timezone.utc).timestamp()}"
        task = ORMTask(
            uuid=task_uuid, status="pending", result=None,
            file_name=file_name, task_type="speech-to-text", user_id=user_id,
        )
        session.add(task)
        session.commit()
        return task_uuid


# ---- JWT forgery helpers (VERIFY-02/03/04) ----
def _b64url(raw: dict | bytes) -> str:
    """JWT-spec base64url: URL-safe, no padding."""
    if isinstance(raw, dict):
        raw = json.dumps(raw, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _forge_jwt(
    *, alg: str, user_id: int, token_version: int = 0,
    secret: str | None = None, expired: bool = False, tamper: bool = False,
) -> str:
    """Forge a JWT for testing.

    alg='none' → unsigned token (RFC 7519 §6.1).
    alg='HS256' + secret + expired=True → real signed token with iat/exp in past.
    alg='HS256' + secret + tamper=True  → real token with last sig char flipped.
    """
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now - 86400 if expired else now,
        "exp": now - 3600 if expired else now + 86400,
        "ver": token_version,
        "method": "session",
    }
    if alg == JWT_ALG_NONE:
        header = {"alg": "none", "typ": "JWT"}
        return f"{_b64url(header)}.{_b64url(payload)}."  # trailing dot, empty sig
    assert secret is not None, "HS256 forge requires secret"
    token = jwt.encode(payload, secret, algorithm=JWT_HS256)
    if tamper:
        head, body, sig = token.split(".")
        flipped = "A" if sig[-1] != "A" else "B"
        return f"{head}.{body}.{sig[:-1]}{flipped}"
    return token


# ---- CSRF helpers (VERIFY-06) ----
def _issue_csrf_pair(client: TestClient, email: str) -> tuple[str, str]:
    """Register user → return (session_cookie_value, csrf_cookie_value)."""
    _register(client, email)
    return client.cookies.get("session"), client.cookies.get("csrf_token")


# ---- Alembic subprocess (VERIFY-08) ----
def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke alembic CLI with DB_URL pointed at the tmp DB."""
    env = os.environ.copy()
    env["DB_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, check=True, capture_output=True, text=True,
    )
```

**Naming contract (locked):**
- `client_a`, `client_b` — never `c1`, `c2`
- `user_a_id`, `user_b_id` — never `uid_a`
- `task_a_uuid`, `task_b_uuid` — never `t1`, `t2`
- `tampered_token`, `expired_token`, `alg_none_token` — never `bad_token`
- `foreign_status`, `self_status` — for endpoint catalog tuples
- `_forge_jwt(alg="none", ...)`, `_forge_jwt(alg="HS256", expired=True, ...)` — kwargs only

## Files to Create

| Path | Purpose | Lines (est.) | Source pattern |
|------|---------|--------------|----------------|
| `tests/integration/_phase16_helpers.py` | DRY shared helpers | ~150 | NEW (composition of existing helpers) |
| `tests/integration/test_security_matrix.py` | VERIFY-01 cross-user matrix | ~250 | test_account_routes.py + test_per_user_scoping.py |
| `tests/integration/test_jwt_attacks.py` | VERIFY-02/03/04 | ~180 | test_auth_routes.py auth_full_app pattern |
| `tests/integration/test_csrf_enforcement.py` | VERIFY-06 | ~150 | test_phase13_e2e_smoke.py:test_csrf_required_on_cookie_post + bearer-bypass |
| `tests/integration/test_ws_ticket_safety.py` | VERIFY-07 (gold copy) | ~200 | test_ws_ticket_flow.py |
| `tests/integration/test_migration_smoke.py` | VERIFY-08 | ~180 | test_alembic_migration.py |

## Files to Modify

**None.** Phase 16 ships test-only files. No app/ touches; no docs/ touches; no alembic/ touches.

## Sources

### Primary (HIGH confidence — verified in repo this session)
- `app/core/jwt_codec.py` — single decode site, HS256-only, typed exception mapping
- `app/core/dual_auth.py` — bearer-then-cookie resolution, public allowlist, 401 on failure
- `app/core/csrf_middleware.py` — double-submit on cookie + state-mutating method
- `app/services/ws_ticket_service.py` — atomic single-use consume, datetime.now expiry, threading.Lock
- `app/api/websocket_api.py` — 5-guard validation chain, 1008 close on any failure
- `app/api/ws_ticket_routes.py` — ticket issue endpoint, scoped-repo for cross-user 404
- `app/api/account_routes.py` — DELETE /api/account + /api/account/data + GET /api/account/me
- `app/api/key_routes.py` — POST/GET/DELETE /api/keys
- `app/api/task_api.py` — GET /tasks, GET/DELETE /task/{id}
- `app/api/audio_api.py` — POST /speech-to-text + /speech-to-text-url
- `app/main.py` — middleware registration order
- `alembic/versions/0001_baseline.py`, `0002_auth_schema.py`, `0003_tasks_user_id_not_null.py`
- `tests/integration/test_account_routes.py` — slim app fixture pattern (DualAuth + DB override)
- `tests/integration/test_auth_routes.py` — auth_full_app fixture (full middleware stack)
- `tests/integration/test_ws_ticket_flow.py` — WS test patterns + _FrozenDatetime monkeypatch
- `tests/integration/test_alembic_migration.py` — subprocess alembic + tmp_path patterns
- `tests/integration/test_phase13_e2e_smoke.py` — subprocess uvicorn + bearer-skips-CSRF + cross-user 404 patterns
- `tests/integration/test_per_user_scoping.py` — task scoping cross-user assertions
- `pyproject.toml` — pytest 9.0.2, pyjwt>=2.8.0, alembic>=1.13.0, slowapi>=0.1.9

### Secondary (MEDIUM confidence — cross-verified with primary)
- `.planning/STATE.md` — Phase 13/14/15 lessons learned (cookie clearing, DELETE-with-body, two-client pattern)
- `.planning/REQUIREMENTS.md` — VERIFY-01..08 definitions
- `.planning/codebase/STRUCTURE.md` + `.planning/codebase/TESTING.md` — pytest configuration baseline

### Tertiary (LOW confidence — training data, flagged for verification)
- PyJWT 2.x rejects alg=none on decode by default — [VERIFIED via app/core/exceptions.py imports `JwtAlgorithmError` and code path in `jwt_codec.py:57`]
- RFC 7519 §6.1 plaintext JWS spec — [CITED, no online verification this session]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version verified in pyproject.toml; no new dependencies
- Architecture: HIGH — five proven fixture patterns reused verbatim; no new patterns invented
- Pitfalls: HIGH — every pitfall comes from a documented Phase 10/13/14/15 STATE.md lesson
- Endpoint catalog: HIGH — derived from grepping every `@router.{method}` in app/api/ this session
- JWT forgery: MEDIUM — direct base64 construction is well-known but should be smoke-tested in Wave 0; expected behavior backed by PyJWT exception class hierarchy verified in `jwt_codec.py`
- Migration smoke: MEDIUM — synthetic baseline schema + 3-step upgrade sequence is novel composition (existing tests don't seed tasks before 0003); assumption that 0003 pre-flight will pass after manual UPDATE is verified by reading 0003.upgrade()

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (30 days; stable test infrastructure, no breaking changes expected in v1.2 phase 17)
