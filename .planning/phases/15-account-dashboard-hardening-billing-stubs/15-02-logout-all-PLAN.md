---
phase: 15
plan: 02
type: execute
wave: 1
depends_on: ["15-01"]
files_modified:
  - app/api/auth_routes.py
  - tests/integration/test_auth_routes.py
autonomous: true
requirements: [AUTH-06]
must_haves:
  truths:
    - "POST /auth/logout-all bumps users.token_version by exactly +1 atomically"
    - "POST /auth/logout-all returns HTTP 204 with Set-Cookie deletions for session + csrf_token"
    - "POST /auth/logout-all requires authentication (401 when called anonymously)"
    - "Old JWT issued before logout-all returns 401 on the next request via the same TestClient"
  artifacts:
    - path: "app/api/auth_routes.py"
      provides: "POST /auth/logout-all route"
      contains: "@auth_router.post(\"/logout-all\""
    - path: "tests/integration/test_auth_routes.py"
      provides: "logout-all integration coverage"
      contains: "def test_logout_all_"
  key_links:
    - from: "app/api/auth_routes.py:logout_all"
      to: "app/services/auth/auth_service.py:logout_all_devices"
      via: "auth_service.logout_all_devices(int(user.id))"
      pattern: "auth_service\\.logout_all_devices"
    - from: "app/api/auth_routes.py:logout_all"
      to: "app/api/_cookie_helpers.py:clear_auth_cookies"
      via: "imported helper called on new Response"
      pattern: "clear_auth_cookies\\(response\\)"
---

<objective>
Wire the new `POST /auth/logout-all` HTTP route to the already-implemented `AuthService.logout_all_devices` (token_version bump). Mirror the existing `/auth/logout` pattern for cookie clearing — return a fresh Response(204) with `clear_auth_cookies(response)` from the shared helper.

Purpose: Close AUTH-06. Glue-only — service + cookie helper both exist (Phase 11 + Plan 15-01). HTTP layer is the missing piece.
Output: One route + four integration test cases in test_auth_routes.py (or test_account_routes.py if DualAuthMiddleware is required for the auth check).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-CONTEXT.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-01-groundwork-PLAN.md
@app/api/auth_routes.py
@app/api/account_routes.py
@app/services/auth/auth_service.py
@tests/integration/test_auth_routes.py
@tests/integration/test_account_routes.py

<interfaces>
<!-- Pulled verbatim from codebase. Executor uses these directly. -->

From app/services/auth/auth_service.py (lines 91-97 — already implemented):
```python
def logout_all_devices(self, user_id: int) -> None:
    user = self.user_repository.get_by_id(user_id)
    if user is None:
        raise InvalidCredentialsError()
    self.user_repository.update_token_version(user_id, user.token_version + 1)
    logger.info("Logout-all-devices id=%s", user_id)
```

From app/api/dependencies.py (existing — ready to import):
```python
get_authenticated_user(...) -> User           # raises 401 if no auth
get_auth_service(...) -> AuthService           # DI factory
```

From app/api/auth_routes.py (existing /logout pattern, lines 182-194 — to mirror):
```python
@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)   # post-Plan 15-01 — imported from _cookie_helpers
    return response
```

From tests/integration/test_account_routes.py (lines 88-117 — slim FastAPI fixture WITH DualAuthMiddleware mounted; required for auth-required routes):
```python
@pytest.fixture
def account_app(tmp_db_url, session_factory):
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

NOTE: `tests/integration/test_auth_routes.py:auth_app` fixture does NOT mount DualAuthMiddleware (it tests anonymous register/login). The /logout-all route requires `get_authenticated_user` → must be tested via the `account_app` style fixture OR via a new fixture. PATTERNS.md §"test_auth_routes.py extend" says "add logout-all tests to `test_account_routes.py`" — follow that locked recommendation.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add POST /auth/logout-all route in auth_routes.py + 4 integration tests</name>
  <files>app/api/auth_routes.py, tests/integration/test_auth_routes.py</files>
  <read_first>
    - app/api/auth_routes.py (full — confirm post-Plan 15-01 state with imports from _cookie_helpers; confirm `auth_router = APIRouter(prefix="/auth")` and existing `get_auth_service` / `get_authenticated_user` imports)
    - app/api/dependencies.py lines 220-260 (get_authenticated_user + get_auth_service signatures)
    - app/services/auth/auth_service.py lines 85-100 (logout_all_devices full implementation)
    - tests/integration/test_account_routes.py lines 1-150 (fixture stack: tmp_db_url, session_factory, account_app, client, _register helper)
    - tests/integration/test_auth_routes.py lines 271-291 (logout test pattern to mirror for cookie-deletion assertions)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"app/api/auth_routes.py (controller, MODIFY: add /logout-all)" + §"tests/integration/test_auth_routes.py (extend)"
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Token-Version Invariant" + §"Backend: New Routes" §930-940
  </read_first>
  <behavior>
    - Test 1 `test_logout_all_bumps_token_version`: register user, read `users.token_version` (= N), POST /auth/logout-all returns 204, re-read token_version (= N+1).
    - Test 2 `test_logout_all_clears_cookies`: response Set-Cookie headers contain `session=` and `csrf_token=` with `Max-Age=0`.
    - Test 3 `test_logout_all_invalidates_existing_jwt`: same TestClient that registered (cookie present) calls /auth/logout-all, then a state-mutating call (e.g., GET /api/account/me — also exercises Plan 15-03 path; OR fall back to a Plan 13 endpoint like POST /api/keys with the now-stale ver) returns 401. NOTE: the fresh response cookie is `session=` cleared, so the **next** TestClient request will not even carry the old cookie. To exercise the token_version invariant explicitly, snapshot the cookie value BEFORE logout-all and re-attach it manually on the next request: `client.cookies.set("session", saved_session_cookie)`. Then assert 401.
    - Test 4 `test_logout_all_requires_auth`: TestClient with no cookies POST /auth/logout-all returns 401.
  </behavior>
  <action>
    Per AUTH-06 (D-RES locked) — wire HTTP route to existing service. **No** double-bump on delete (separate plan); **no** session-blacklist (rely on token_version + middleware ver-check, T-15-03 mitigation).

    **1a. Modify `app/api/auth_routes.py`:** add the route. Insert after the existing `/logout` route (around line 194). The required imports (`get_auth_service`, `get_authenticated_user`, `clear_auth_cookies`, `User`, `AuthService`) should already be in the file post-Plan 15-01; verify and add any that are missing.

    Route body verbatim (RESEARCH §930-940):
    ```python
    @auth_router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
    async def logout_all(
        user: User = Depends(get_authenticated_user),
        auth_service: AuthService = Depends(get_auth_service),
    ) -> Response:
        """POST /auth/logout-all — bump token_version + clear cookies. AUTH-06.

        Invalidates every JWT issued for this user (including the caller's own
        cookie) by bumping users.token_version. The next middleware ver-check
        will 401 any outstanding session. Cookie clearing is for client UX —
        the JWTs are already dead.
        """
        auth_service.logout_all_devices(int(user.id))
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response
    ```

    Tiger-style: assertions live in `AuthService.logout_all_devices` (already validates user exists). Route is glue.
    SRP: route does HTTP only. No business logic.
    No nested-if: route body has zero `if` statements. Auth gate is in `get_authenticated_user`.

    **1b. Extend `tests/integration/test_auth_routes.py`** with 4 test cases. Per PATTERNS.md §"tests/integration/test_auth_routes.py (extend)" recommendation, **add the tests using a fixture that mounts DualAuthMiddleware**. Two paths:

    Option A (preferred — minimal new code): Add the tests to test_auth_routes.py but ensure the fixture mounts DualAuthMiddleware. Inspect the existing `auth_app` fixture in test_auth_routes.py — if it does NOT mount DualAuthMiddleware, copy the fixture stack from test_account_routes.py:88-117 into test_auth_routes.py as a new `auth_full_app` fixture (or extend `auth_app` itself if no existing test breaks).

    Option B (fallback): Place the tests in test_account_routes.py which already has the right fixture (per PATTERNS.md §"locked recommendation"). If the existing test_auth_routes.py auth_app cannot trivially be extended without breaking other tests, use Option B.

    Test code (using fixture name `client` + `session_factory` as in account fixture):
    ```python
    from sqlalchemy import text
    # ... existing imports ...

    @pytest.mark.integration
    def test_logout_all_bumps_token_version(client, session_factory):
        user_id = _register(client, "logoutall-bump@example.com")
        with session_factory() as session:
            v_before = session.execute(
                text("SELECT token_version FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).scalar_one()

        response = client.post("/auth/logout-all")

        assert response.status_code == 204
        with session_factory() as session:
            v_after = session.execute(
                text("SELECT token_version FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).scalar_one()
        assert v_after == v_before + 1


    @pytest.mark.integration
    def test_logout_all_clears_cookies(client):
        _register(client, "logoutall-cookies@example.com")

        response = client.post("/auth/logout-all")

        assert response.status_code == 204
        set_cookie_headers = response.headers.get_list("set-cookie")
        joined = "\n".join(set_cookie_headers).lower()
        assert "session=" in joined
        assert "csrf_token=" in joined
        assert joined.count("max-age=0") == 2


    @pytest.mark.integration
    def test_logout_all_invalidates_existing_jwt(client, session_factory):
        _register(client, "logoutall-invalidate@example.com")
        # Snapshot the cookie BEFORE logout-all clears it client-side
        old_session_cookie = client.cookies.get("session")
        assert old_session_cookie is not None

        first_response = client.post("/auth/logout-all")
        assert first_response.status_code == 204

        # Re-attach the now-stale cookie (token_version is N, server expects N+1)
        client.cookies.set("session", old_session_cookie)
        retry = client.post("/auth/logout-all")
        assert retry.status_code == 401


    @pytest.mark.integration
    def test_logout_all_requires_auth(account_app):
        from fastapi.testclient import TestClient
        app, _ = account_app
        anon = TestClient(app)

        response = anon.post("/auth/logout-all")

        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"
    ```

    Naming locked per CLAUDE.md self-explanatory: `v_before`/`v_after` over `vb`/`va`; `old_session_cookie` over `ck`.
  </action>
  <verify>
    <automated>pytest tests/integration/test_auth_routes.py -k "logout_all" -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "@auth_router.post(\"/logout-all\"" app/api/auth_routes.py` returns 1
    - `grep -c "auth_service.logout_all_devices" app/api/auth_routes.py` returns 1
    - `grep -c "clear_auth_cookies(response)" app/api/auth_routes.py` returns at least 2 (logout + logout-all)
    - `grep -cE "^\s+if .*\bif\b" app/api/auth_routes.py` returns 0
    - `grep -c "Depends(Response)" app/api/auth_routes.py` returns 0 (cookie-deletion anti-pattern T-15-04 absent)
    - `pytest tests/integration/test_auth_routes.py -k "logout_all" -q` reports exactly 4 passing tests
    - All 4 must-have truths verified by these tests
    - Existing `/auth/logout` tests continue to pass (no regression)
  </acceptance_criteria>
  <done>POST /auth/logout-all wired; 4 integration tests green; token_version bump verified; old JWT invalidation verified; auth gate verified; cookies cleared verified.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → DualAuthMiddleware → /auth/logout-all | Untrusted cookie session JWT verified before route entry |
| Service → users.token_version row | Atomic UPDATE — single SQL statement, no race window |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-15-03 | Information Disclosure | Token bump race vs in-flight requests | mitigate | UPDATE commits before response sent; concurrent ver=N JWT 401s on next middleware lookup (verify_and_refresh `payload.get("ver") != current_token_version`); `test_logout_all_invalidates_existing_jwt` exercises this path |
| T-15-04 | Information Disclosure | Cookie-deletion headers dropped | mitigate | Mirror /auth/logout: build new `Response(204)`, call `clear_auth_cookies(response)`, return that. Verifier-grep `Depends(Response)` returns 0 in auth_routes.py |
| T-15-09 | Information Disclosure | Cross-tab logout-all not synced | accept | Phase 15-06 caller invokes `authStore.logout()` after receiving 204; BroadcastChannel('auth') broadcasts logout to all tabs (UI-12 existing). Server-side phase 15-02 has no cross-tab responsibility. |
| T-13-13 | Information Disclosure | Email/token leaked in route logs | mitigate | Service-layer `logger.info("Logout-all-devices id=%s", user_id)` logs id only (verified auth_service.py:96); route adds zero logging |
</threat_model>

<verification>
- All 4 logout-all tests pass via `pytest tests/integration/test_auth_routes.py -k logout_all -x -q`
- Existing /auth/logout tests still pass: `pytest tests/integration/test_auth_routes.py -k "logout and not logout_all" -q`
- T-15-04 verifier-grep `Depends(Response)` returns 0 across new code
- Nested-if verifier `grep -cE "^\s+if .*\bif\b" app/api/auth_routes.py` returns 0
</verification>

<success_criteria>
1. POST /auth/logout-all bumps users.token_version atomically (+1)
2. Response is 204 with Set-Cookie deletions for session + csrf_token
3. JWT issued before logout-all returns 401 on next authenticated request (token_version invariant)
4. Anonymous POST /auth/logout-all returns 401 "Authentication required"
</success_criteria>

<output>
After completion, create `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-02-SUMMARY.md`
</output>
