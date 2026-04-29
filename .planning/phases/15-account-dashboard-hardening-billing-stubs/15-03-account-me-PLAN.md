---
phase: 15
plan: 03
type: execute
wave: 1
depends_on: ["15-01"]
files_modified:
  - app/services/account_service.py
  - app/api/account_routes.py
  - tests/integration/test_account_routes.py
autonomous: true
requirements: [UI-07]
must_haves:
  truths:
    - "GET /api/account/me returns AccountSummaryResponse with user_id, email, plan_tier, trial_started_at, token_version"
    - "GET /api/account/me returns 401 'Authentication required' for anonymous requests"
    - "AccountService.get_account_summary reads from injected user_repository (not session.execute)"
    - "AccountService constructor stays backward-compatible with existing /data callers (user_repository optional)"
  artifacts:
    - path: "app/api/account_routes.py"
      provides: "GET /api/account/me route"
      contains: "@account_router.get(\"/me\""
    - path: "app/services/account_service.py"
      provides: "get_account_summary + extended __init__ with user_repository"
      contains: "def get_account_summary"
    - path: "tests/integration/test_account_routes.py"
      provides: "/me happy path + 401 + shape coverage"
      contains: "def test_get_account_me_"
  key_links:
    - from: "app/api/account_routes.py:get_account_me"
      to: "app/services/account_service.py:get_account_summary"
      via: "account_service.get_account_summary(int(user.id))"
      pattern: "account_service\\.get_account_summary"
    - from: "app/services/account_service.py:get_account_summary"
      to: "app/domain/repositories/user_repository.py:IUserRepository.get_by_id"
      via: "self._user_repository.get_by_id(user_id)"
      pattern: "_user_repository\\.get_by_id"
---

<objective>
Wire `GET /api/account/me` to a new `AccountService.get_account_summary(user_id)` method. This is the server-side hydration source-of-truth used by `authStore.refresh()` (Plan 15-05) and `AccountPage` (Plan 15-06). Pure read — no mutations.

Purpose: Bridge UI-07 from "client-stored email from form input" (Plan 14-03 trade-off) to "server-authoritative user state on every page load."
Output: One service method + one route + 3 integration tests.
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
@app/api/account_routes.py
@app/services/account_service.py
@app/domain/repositories/user_repository.py
@app/infrastructure/database/repositories/sqlalchemy_user_repository.py
@app/api/schemas/account_schemas.py
@tests/integration/test_account_routes.py

<interfaces>
<!-- Pulled from codebase. Use directly. -->

From app/api/schemas/account_schemas.py (created in Plan 15-01):
```python
class AccountSummaryResponse(BaseModel):
    user_id: int
    email: EmailStr
    plan_tier: str = Field(..., description="One of free|trial|pro|team")
    trial_started_at: datetime | None = None
    token_version: int = Field(..., description="For cross-tab refresh debounce")
```

From app/domain/repositories/user_repository.py (existing IUserRepository Protocol):
```python
class IUserRepository(Protocol):
    def get_by_id(self, user_id: int) -> User | None: ...
    def get_by_email(self, email: str) -> User | None: ...
    def add(self, user: User) -> User: ...
    def update_token_version(self, user_id: int, token_version: int) -> None: ...
    def delete(self, user_id: int) -> bool: ...
```

From app/domain/entities/user.py:
```python
class User:
    id: int | None
    email: str
    plan_tier: str
    trial_started_at: datetime | None
    token_version: int
    # password_hash + bump_token_version() etc.
```

From app/services/account_service.py (current state — to extend):
```python
class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def delete_user_data(self, user_id: int) -> dict[str, int]:
        # ... existing SCOPE-05 path, do NOT modify
```

From app/api/dependencies.py (existing — both ready):
```python
get_authenticated_user(...) -> User
get_account_service(...) -> AccountService
```

From app/api/account_routes.py (current routes — DELETE /data exists, mirror its style):
```python
account_router = APIRouter(prefix="/api/account")

@account_router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_data(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    account_service.delete_user_data(int(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend AccountService with constructor user_repository (default None lazy-construct) + get_account_summary method</name>
  <files>app/services/account_service.py</files>
  <read_first>
    - app/services/account_service.py (full — preserve `delete_user_data` SCOPE-05 path; verify constructor signature)
    - app/domain/repositories/user_repository.py (full IUserRepository Protocol)
    - app/infrastructure/database/repositories/sqlalchemy_user_repository.py lines 1-50 (constructor + get_by_id implementation)
    - app/domain/entities/user.py (User entity fields)
    - app/core/exceptions.py — InvalidCredentialsError
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"app/services/account_service.py" (constructor extension + get_account_summary)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Backend: account_service.delete_account [PRESCRIPTIVE TEMPLATE]" §884-896 (get_account_summary template) + §899 (constructor extension)
  </read_first>
  <behavior>
    - `AccountService(session)` (no user_repository) still works — backward compat for existing /data callers (SCOPE-05).
    - `AccountService(session, user_repository=fake_repo).get_account_summary(uid)` returns dict with user_id/email/plan_tier/trial_started_at/token_version when fake_repo.get_by_id(uid) returns a User entity.
    - `get_account_summary(uid)` raises `InvalidCredentialsError` when repository returns None (anti-enumeration generic error).
    - `get_account_summary(0)` or negative — boundary assertion fails loud (AssertionError).
  </behavior>
  <action>
    Per D-RES locked: constructor-inject user_repository (default None, lazy-construct from session). DRY for both `get_account_summary` and (Plan 15-04) `delete_account`.

    Modify `app/services/account_service.py`:

    1. Add imports near the top:
    ```python
    from app.core.exceptions import InvalidCredentialsError
    from app.domain.repositories.user_repository import IUserRepository
    from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
        SQLAlchemyUserRepository,
    )
    ```

    2. Replace `__init__` with the extended version (preserving the `session` attribute name):
    ```python
    def __init__(
        self,
        session: Session,
        user_repository: IUserRepository | None = None,
    ) -> None:
        self.session = session
        # SCOPE-05 callers pass session only; lazy-construct keeps them working.
        # Plan 15-03 + 15-04 callers inject the repo for testability.
        self._user_repository: IUserRepository = (
            user_repository or SQLAlchemyUserRepository(session)
        )
    ```

    3. Add the new method after `delete_user_data`:
    ```python
    def get_account_summary(self, user_id: int) -> dict:
        """GET /api/account/me service path — pure read of users row.

        Returns dict matching AccountSummaryResponse schema field names.
        Raises InvalidCredentialsError (generic, anti-enumeration) on missing user.
        """
        # Tiger-style boundary assertion
        assert user_id > 0, "user_id must be positive"

        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError()

        return {
            "user_id": int(user.id),
            "email": user.email,
            "plan_tier": user.plan_tier,
            "trial_started_at": user.trial_started_at,
            "token_version": user.token_version,
        }
    ```

    Tiger-style: assertion at boundary; fail-loud on missing user; no silent None return.
    SRP: service does business logic; repository owns persistence.
    DRY: `_user_repository` member shared with Plan 15-04 `delete_account`.
    No nested-if: one flat guard clause + one return.
    Naming: `_user_repository` (single underscore — module-internal, not name-mangled); not `_repo` or `ur`.

    Do not write tests in this task — Task 2 covers them via integration tests of the route.
  </action>
  <verify>
    <automated>python -c "from app.services.account_service import AccountService; from app.infrastructure.database.connection import get_engine; from sqlalchemy.orm import Session; print('module import OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def get_account_summary" app/services/account_service.py` returns 1
    - `grep -c "user_repository: IUserRepository | None = None" app/services/account_service.py` returns 1
    - `grep -c "self._user_repository" app/services/account_service.py` >= 1
    - `grep -c "assert user_id > 0" app/services/account_service.py` returns 1
    - `grep -cE "^\s+if .*\bif\b" app/services/account_service.py` returns 0
    - `python -c "from app.services.account_service import AccountService"` exits 0 (no import-time crash)
    - `pytest tests/integration/test_account_routes.py -k delete_user_data -q` still green (SCOPE-05 backward compat preserved)
  </acceptance_criteria>
  <done>Service compiles + imports; existing /data tests pass; new method exists with boundary assertions and generic-error guard.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add GET /api/account/me route + 3 integration tests</name>
  <files>app/api/account_routes.py, tests/integration/test_account_routes.py</files>
  <read_first>
    - app/api/account_routes.py (full — current route mounting + get_account_service factory at lines 27-31)
    - app/api/dependencies.py (get_authenticated_user, get_account_service)
    - app/api/schemas/account_schemas.py (AccountSummaryResponse from Plan 15-01)
    - tests/integration/test_account_routes.py (existing fixtures + _register helper at lines 55-117 + auth-required test pattern at lines 263-272)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"app/api/account_routes.py" + §"tests/integration/test_account_routes.py"
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Backend: New Routes" §905-925
  </read_first>
  <behavior>
    - Test 1 `test_get_account_me_returns_summary`: register Alice, GET /api/account/me, assert 200 + body has user_id/email/plan_tier/trial_started_at/token_version with the registered email.
    - Test 2 `test_get_account_me_requires_auth`: anon TestClient GET /api/account/me returns 401 + `detail == "Authentication required"`.
    - Test 3 `test_get_account_me_response_shape_locked`: response JSON keys are exactly the 5 declared fields (no extras), email matches registered, token_version is an int (initial 0).

    Note `get_account_service` from `app/api/dependencies.py` already takes a session; per Plan 15-03 Task 1, AccountService is now constructed with session-only by that factory and lazy-constructs the user repository. This works without dependency factory changes — verify in plan-checker if needed.
  </behavior>
  <action>
    Per D-RES locked: route is HTTP glue; service does the read.

    **2a. Modify `app/api/account_routes.py`** — add the GET /me route. Insert after the existing `delete_user_data` route.

    Required new imports at file head:
    ```python
    from app.api.schemas.account_schemas import AccountSummaryResponse
    ```

    Route body verbatim (RESEARCH §905-913):
    ```python
    @account_router.get("/me", response_model=AccountSummaryResponse)
    async def get_account_me(
        user: User = Depends(get_authenticated_user),
        account_service: AccountService = Depends(get_account_service),
    ) -> AccountSummaryResponse:
        """GET /api/account/me — return summary for client hydration. UI-07."""
        summary = account_service.get_account_summary(int(user.id))
        return AccountSummaryResponse(**summary)
    ```

    SRP: route does HTTP only — service-layer guard handles missing user via InvalidCredentialsError → 401 (existing exception_handler).
    No nested-if: zero `if` statements in route body.

    **2b. Extend `tests/integration/test_account_routes.py`** with 3 tests:
    ```python
    @pytest.mark.integration
    def test_get_account_me_returns_summary(client):
        email = "alice-me@example.com"
        _register(client, email)

        response = client.get("/api/account/me")

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == email
        assert body["plan_tier"] in {"trial", "free", "pro", "team"}
        assert isinstance(body["user_id"], int)
        assert body["user_id"] > 0
        assert isinstance(body["token_version"], int)
        # trial_started_at can be null (no API key created yet)
        assert "trial_started_at" in body


    @pytest.mark.integration
    def test_get_account_me_requires_auth(account_app):
        from fastapi.testclient import TestClient
        app, _ = account_app
        anon = TestClient(app)

        response = anon.get("/api/account/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"


    @pytest.mark.integration
    def test_get_account_me_response_shape_locked(client):
        email = "alice-shape@example.com"
        _register(client, email)

        response = client.get("/api/account/me")

        assert response.status_code == 200
        body = response.json()
        # Locked field set per AccountSummaryResponse — no extras leaked
        assert set(body.keys()) == {
            "user_id",
            "email",
            "plan_tier",
            "trial_started_at",
            "token_version",
        }
    ```

    Naming: `body` (matches existing helper pattern); `email` (full word).
  </action>
  <verify>
    <automated>pytest tests/integration/test_account_routes.py -k "get_account_me" -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "@account_router.get(\"/me\"" app/api/account_routes.py` returns 1
    - `grep -c "response_model=AccountSummaryResponse" app/api/account_routes.py` returns 1
    - `grep -c "account_service.get_account_summary" app/api/account_routes.py` returns 1
    - `grep -c "from app.api.schemas.account_schemas import" app/api/account_routes.py` returns 1
    - `grep -cE "^\s+if .*\bif\b" app/api/account_routes.py` returns 0
    - `pytest tests/integration/test_account_routes.py -k "get_account_me" -q` reports exactly 3 passing tests
    - Existing `delete_user_data` tests (`test_delete_user_data_*`) all still pass
  </acceptance_criteria>
  <done>GET /api/account/me works; 3 integration tests green; response shape locked; auth gate enforced; no regression on /data.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → DualAuthMiddleware → /api/account/me | Cookie session JWT verified before route entry; ver-check enforces token_version invariant |
| Service → users row | Pure read; no mutation, no transaction needed |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-15-11 | Information Disclosure | Schema leaking sensitive fields | mitigate | AccountSummaryResponse exposes only 5 fields (user_id/email/plan_tier/trial_started_at/token_version); password_hash + token columns NEVER serialized; test_get_account_me_response_shape_locked enforces |
| T-15-04 | Information Disclosure | /me anonymous access | mitigate | get_authenticated_user dependency raises 401 before route body executes; test_get_account_me_requires_auth enforces |
| T-13-13 | Information Disclosure | Email logged at route level | mitigate | No new logging in route; service path doesn't log on the read either; only structured `user_id` references in logs |
| T-15-05 | Information Disclosure | User-not-found differential vs auth-failure | mitigate | InvalidCredentialsError returns 401 (same shape as auth-failure); 404-vs-401 not differentiable post-auth (unreachable: authenticated user always exists in DB at request time) |
</threat_model>

<verification>
- All 3 /me tests pass via `pytest tests/integration/test_account_routes.py -k get_account_me -x -q`
- Existing /data tests pass: `pytest tests/integration/test_account_routes.py -k delete_user_data -q`
- Logout-all tests from Plan 15-02 still pass (no fixture clobbering)
- T-15-11 verifier: response keys exactly match the 5-field set — extras would fail
- Nested-if verifier: 0 across modified files
</verification>

<success_criteria>
1. GET /api/account/me returns 200 + AccountSummaryResponse-shaped JSON for authenticated user
2. GET /api/account/me returns 401 "Authentication required" for anonymous request
3. AccountService(session) two-arg invocation still works for SCOPE-05 backward compat
4. AccountService(session, user_repository=...) injection works for new methods
5. Response body keys are exactly {user_id, email, plan_tier, trial_started_at, token_version} — no extras
</success_criteria>

<output>
After completion, create `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-03-SUMMARY.md`
</output>
