# Phase 16: Verification + Cross-User Matrix + E2E - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning
**Mode:** Smart-discuss (single grey area accepted as recommended)

<domain>
## Phase Boundary

Every critical security invariant from v1.2 is asserted by automated tests. Phase 16 is the milestone gate — green test suite proves cross-user isolation, JWT hardening, CSRF enforcement, WS ticket safety, and migration correctness.

In scope:
- **Cross-user matrix** (VERIFY-01) — pytest parametrized fixture seeds User A + User B + tasks/keys/usage. For every task-touching endpoint (GET/DELETE /tasks, GET /task/{id}, POST /speech-to-text*, TUS upload, WS, callbacks, DELETE /api/account/data, DELETE /api/account, GET /api/account/me), User B receives 404/403 attempting to access User A's resources — and vice versa.
- **JWT attack tests** (VERIFY-02..04) — alg=none → 401, tampered signature → 401, expired token → 401. Forged token construction via direct base64 encode (no library that refuses alg=none).
- **CSRF integration tests** (VERIFY-06) — cookie-auth state-mutating request without X-CSRF-Token → 403; with mismatched header → 403; with matching header → success.
- **WebSocket ticket flow tests** (VERIFY-07) — ticket reuse → 1008 close, expired ticket (>60s mocked clock) → 1008, ticket whose user_id != task.user_id → 1008.
- **Migration smoke test** (VERIFY-08) — copy production-style records.db to tmp_path, run alembic stamp baseline → alembic upgrade head, verify all tasks.user_id resolve to seeded admin, all FK constraints enforce, no data loss.
- All tests live in `tests/integration/`. Each VERIFY ID cluster gets its own file.

Out of scope:
- New Playwright e2e specs (Phase 15 added Playwright suite for AccountPage; Phase 16 stays backend-Python-only).
- New runtime code changes — Phase 16 is verification only. If a test exposes a regression, file as a hot-fix in a separate phase.
- Performance benchmarks (VERIFY-05 was Argon2 hash benchmark — already complete in Phase 11).

</domain>

<decisions>
## Implementation Decisions

### Test File Layout

- `tests/integration/test_security_matrix.py` — VERIFY-01 cross-user matrix (parametrized table)
- `tests/integration/test_jwt_attacks.py` — VERIFY-02, VERIFY-03, VERIFY-04
- `tests/integration/test_csrf_enforcement.py` — VERIFY-06
- `tests/integration/test_ws_ticket_safety.py` — VERIFY-07
- `tests/integration/test_migration_smoke.py` — VERIFY-08

### Cross-User Matrix Strategy

- pytest parametrize over endpoint × {self, foreign} → expected status assertions
- Two TestClient instances, separate cookie jars, same app + DB
- Endpoint catalog hardcoded as module-level constant (DRY single source)
- Every endpoint must produce the same opaque 404 body for unknown-id and foreign-id (anti-enumeration parity already proven in Plan 13-07; this phase verifies it)

### JWT Attack Strategy

- Forge tokens by direct `header64.payload64.signature64` construction (bypass library validation)
- alg=none token: header={"alg":"none","typ":"JWT"}, payload=valid sub, signature=""
- Tampered: take valid token, flip last char of signature
- Expired: issue with iat=now-86400, exp=now-3600 (must use real signing key but past expiry)
- Each test sends token via Authorization: Bearer header AND via session cookie — both paths must 401

### CSRF Strategy

- Use existing TestClient session login flow → captures both `session` + `csrf_token` cookies
- 3 test cases per state-mutating endpoint: missing X-CSRF-Token, mismatched X-CSRF-Token, matching X-CSRF-Token
- Bearer auth (API key) tests: confirm CSRF check skipped (header absent → still succeeds)

### WS Ticket Strategy

- Mock `time.monotonic` for expired-ticket test (>60s without sleeping in real time)
- Direct in-memory ticket store inspection — Phase 13 used dict + threading.Lock; tests can introspect via the singleton
- Cross-user ticket: issue ticket for User A's task, attempt to consume with User B's connection identity → 1008 close

### Migration Smoke Strategy

- Use a snapshot SQLite file in `tests/fixtures/migration/records-v1.1.db` if present, else build a synthetic baseline schema in-test
- Copy to `tmp_path` so test is isolated
- Run `subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env={DB_URL: tmp_db})` — venv-portable per Plan 10-04 lesson
- Assertions: tasks.user_id IS NOT NULL for all rows, foreign keys enforce, row count preserved, admin user seeded

### Code Quality Invariants

- DRY: shared `_seed_two_users(session)` fixture; single `_endpoint_catalog` constant; reuse Phase 15 `_seed_full_user_universe` if applicable
- SRP: one test file per VERIFY cluster
- Tiger-style: assertions at boundaries; explicit error-message asserts (not just status codes)
- No nested-if (verifier grep returns 0 across new test files)
- Self-explanatory names: `tampered_token` not `t`, `foreign_user_client` not `c2`

### Claude's Discretion

- Exact pytest fixture composition (use existing `tests/conftest.py` patterns)
- Choice of how to forge alg=none tokens (urlsafe_b64encode of JSON works)
- Whether migration smoke uses `subprocess.run` or `alembic.command.upgrade` API directly — pick whichever produces fewer flaky cases on Windows

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `tests/integration/test_account_routes.py` — pattern for slim FastAPI fixture + DualAuthMiddleware mounting
- `tests/integration/test_auth_routes.py` — auth_full_app fixture with Container override (Plan 15-02)
- `tests/integration/test_atomic_e2e_smoke.py` — subprocess-driven uvicorn for true end-to-end
- `tests/integration/test_alembic_migration.py` (Phase 10) — pattern for tmp DB + alembic invocation
- `app/core/jwt_codec.py` — single decode site; `algorithms=["HS256"]` enforces alg-none rejection
- `app/core/csrf_service.py` — issue + verify methods
- `app/api/ws_ticket_routes.py` + `app/api/ws_routes.py` — ticket issue/consume flow
- alembic migrations 0001..0003 + (if exists) 0004 in `alembic/versions/`
- `app/cli/_helpers.py` — `_get_container()` factory test seam

### Integration Points

- Existing `tests/integration/conftest.py` provides DB engine fixture and Container factory — reuse, do not rebuild
- `pytest.ini` already configured for integration tests
- New test files become part of `pytest tests/integration/` suite — no new framework needed

</code_context>

<specifics>
## Specific Ideas

- DRY, SRP, tiger-style, no nested-if, self-explanatory naming — all verifier-grep enforced
- Phase 16 is the milestone gate — failing any new test should block release
- All forged tokens must be reproducible (deterministic — no random secrets)

</specifics>

<deferred>
## Deferred Ideas

- Real load test / fuzzing — not in v1.2
- Cypress / Playwright cross-user matrix — Phase 15 e2e suite covers UI; backend matrix suffices
- Dependency pin audit — out of scope

</deferred>
