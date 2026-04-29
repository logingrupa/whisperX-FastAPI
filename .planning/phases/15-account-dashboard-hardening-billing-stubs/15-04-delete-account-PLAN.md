---
phase: 15
plan: 04
type: execute
wave: 1
depends_on: ["15-01", "15-03"]
files_modified:
  - app/services/account_service.py
  - app/api/account_routes.py
  - tests/integration/test_account_routes.py
autonomous: true
requirements: [SCOPE-06]
must_haves:
  truths:
    - "DELETE /api/account with valid email_confirm cascades to all 6 dependent tables (tasks, api_keys, subscriptions, usage_events, device_fingerprints, rate_limit_buckets) and removes the users row"
    - "DELETE /api/account with mismatched email_confirm returns 400 with EMAIL_CONFIRM_MISMATCH code, preserves all data"
    - "DELETE /api/account is case-insensitive on email match (Foo@Example.com matches stored foo@example.com)"
    - "DELETE /api/account clears session + csrf cookies on success"
    - "DELETE /api/account requires authentication (401 anonymous)"
    - "DELETE /api/account does NOT delete other users' data (smoke isolation)"
  artifacts:
    - path: "app/api/account_routes.py"
      provides: "DELETE /api/account route"
      contains: "@account_router.delete(\"\""
    - path: "app/services/account_service.py"
      provides: "AccountService.delete_account method (cascade orchestration)"
      contains: "def delete_account"
    - path: "tests/integration/test_account_routes.py"
      provides: "6 cascade/email-mismatch/cookies/auth/cross-user tests"
      contains: "def test_delete_account_"
  key_links:
    - from: "app/api/account_routes.py:delete_account"
      to: "app/services/account_service.py:delete_account"
      via: "account_service.delete_account(int(user.id), body.email_confirm)"
      pattern: "account_service\\.delete_account"
    - from: "app/services/account_service.py:delete_account"
      to: "app/services/account_service.py:delete_user_data"
      via: "self.delete_user_data(user_id) — Step 1 cascade for tasks + files"
      pattern: "self\\.delete_user_data"
    - from: "app/services/account_service.py:delete_account"
      to: "rate_limit_buckets table"
      via: "DELETE WHERE bucket_key LIKE 'user:<uid>:%'"
      pattern: "DELETE FROM rate_limit_buckets WHERE bucket_key LIKE"
    - from: "app/api/account_routes.py:delete_account"
      to: "app/api/_cookie_helpers.py:clear_auth_cookies"
      via: "clear_auth_cookies(new Response(204))"
      pattern: "clear_auth_cookies\\(response\\)"
---

<objective>
Implement `DELETE /api/account` end-to-end: AccountService.delete_account orchestrates the multi-step cascade (delete_user_data → rate_limit_buckets prefix-match → user_repository.delete to fire FK CASCADE) plus the email_confirm guard. Route returns 204 + cleared cookies on success, 400 generic on mismatch.

Purpose: Close SCOPE-06. Highest-criticality finding from RESEARCH §428-465 — `tasks.user_id ON DELETE SET NULL` (not CASCADE) and `rate_limit_buckets` has no FK; service-orchestrated delete is the locked strategy.
Output: One service method + one route + 6 integration tests covering the full FK matrix.
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
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-03-account-me-PLAN.md
@app/api/account_routes.py
@app/services/account_service.py
@app/infrastructure/database/models.py
@app/infrastructure/database/repositories/sqlalchemy_user_repository.py
@app/core/exceptions.py
@tests/integration/test_account_routes.py

<interfaces>
<!-- Pulled from codebase. Use directly. -->

From app/infrastructure/database/models.py — FK matrix (audited in RESEARCH §432-441):
| Table | FK column | nullable | ondelete |
|-------|-----------|----------|----------|
| tasks | user_id | NOT NULL (after migration 0003) | **SET NULL** ← cannot bare-delete user |
| api_keys | user_id | NOT NULL | CASCADE |
| subscriptions | user_id | NOT NULL | CASCADE |
| usage_events | user_id | NOT NULL | CASCADE |
| device_fingerprints | user_id | NOT NULL | CASCADE |
| rate_limit_buckets | (no FK; bucket_key text key like `user:42:hour`) | n/a | n/a ← prefix-match required |

From app/services/account_service.py (post-Plan 15-03 state):
- `__init__(session, user_repository=None)` — repo lazy-constructed if absent
- `delete_user_data(user_id)` exists (SCOPE-05 path — DELETEs tasks + on-disk files)
- `_user_repository: IUserRepository` exposed via constructor

From app/domain/repositories/user_repository.py:
```python
class IUserRepository(Protocol):
    def delete(self, user_id: int) -> bool: ...
```
SQLAlchemy impl at sqlalchemy_user_repository.py:122-137 calls `session.delete(orm_user)` + `commit` — fires CASCADE for the 4 CASCADE FKs.

From app/core/exceptions.py:
```python
class InvalidCredentialsError(Exception): pass    # generic anti-enumeration
class ValidationError(Exception):
    def __init__(self, message: str, code: str, user_message: str): ...
```
ValidationError is mapped by validation_error_handler — confirm whether it surfaces as 400 or 422 by reading the handler code, then use the route-level approach below if it defaults to 422.

From app/api/_cookie_helpers.py (Plan 15-01):
```python
def clear_auth_cookies(response: Response) -> None: ...
```

From app/api/schemas/account_schemas.py (Plan 15-01):
```python
class DeleteAccountRequest(BaseModel):
    email_confirm: EmailStr = Field(...)
```

Route prefix: `account_router = APIRouter(prefix="/api/account")`. The new route is `@account_router.delete("")` so the full path is `DELETE /api/account` (note: empty path string maps to the prefix root).

bucket_key naming convention (from app/services/free_tier_gate.py:80,175,214 — verified):
- `user:{uid}:hour` (transcribe count)
- `user:{uid}:tx:hour` (alt naming)
- `user:{uid}:audio_min:day` (daily audio)
- `user:{uid}:concurrent` (concurrency slot)
- `ip:10.0.0.0/24:register:hour` ← MUST NOT match user-prefix
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: AccountService.delete_account — service-orchestrated cascade with email-confirm guard</name>
  <files>app/services/account_service.py</files>
  <read_first>
    - app/services/account_service.py (full — preserve delete_user_data + post-Plan 15-03 constructor with `_user_repository`)
    - app/core/exceptions.py — InvalidCredentialsError, ValidationError signatures
    - app/infrastructure/database/repositories/sqlalchemy_user_repository.py:122-137 — `delete()` impl uses `session.delete(orm_user)` + `commit()`; ORM CASCADE fires for the 4 CASCADE FKs
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"app/services/account_service.py" `delete_account` template
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"FK Cascade Coverage" §428-465 + §"Common Pitfalls" Pitfalls 2/3/4 + §"Backend: account_service.delete_account [PRESCRIPTIVE TEMPLATE]" §836-881
    - app/services/free_tier_gate.py lines 75-90 + 170-220 (bucket_key naming pattern reference for the `user:<uid>:%` LIKE filter)
  </read_first>
  <behavior>
    - Test 1 `test_delete_account_cascade_full_universe` (covered in Task 3): seed 1 row each in tasks/api_keys/subscriptions/usage_events/device_fingerprints/rate_limit_buckets (`user:<uid>:hour`); call delete_account(uid, email); assert COUNT(*) WHERE user_id=:uid is 0 in all 5 FK tables; assert COUNT(*) WHERE bucket_key LIKE 'user:<uid>:%' is 0; assert users row is gone.
    - Test 2: email_confirm mismatch raises ValidationError with code='EMAIL_CONFIRM_MISMATCH'; user row + tasks intact.
    - Test 3: case-insensitive — 'FOO@Example.com' matches stored 'foo@example.com'.
    - Test 4: missing user (uid not in DB) raises InvalidCredentialsError.
    - Test 5: boundary — `delete_account(0, 'x')` AssertionError.
  </behavior>
  <action>
    Per RESEARCH §"Cascade Strategy Decision" Strategy C (LOCKED): service-orchestrated explicit pre-delete + ORM cascade. Order matters — see Pitfall 2 (tasks.user_id NOT NULL after migration 0003).

    Modify `app/services/account_service.py`:

    1. Add imports if not present (Plan 15-03 added InvalidCredentialsError; add ValidationError):
    ```python
    from app.core.exceptions import InvalidCredentialsError, ValidationError
    from sqlalchemy import text   # already imported by delete_user_data
    ```

    2. Add `delete_account` method after `get_account_summary` (Plan 15-03 added that):
    ```python
    def delete_account(self, user_id: int, email_confirm: str) -> dict[str, int]:
        """SCOPE-06: full-row delete + cascade. Email-confirm verified (defence-in-depth).

        Cascade strategy (RESEARCH §"FK Cascade Coverage" — Strategy C LOCKED):
        Step 1: delete_user_data(uid)            tasks (SET NULL FK) + on-disk files
        Step 2: DELETE rate_limit_buckets        no FK; bucket_key text prefix match
        Step 3: user_repository.delete(uid)      ORM cascade fires for the 4 CASCADE FKs
                                                 (api_keys, subscriptions, usage_events,
                                                  device_fingerprints)

        Returns: {tasks_deleted, files_deleted, rate_limit_buckets_deleted}.
        Raises:
            InvalidCredentialsError — user not found (anti-enumeration, T-15-05)
            ValidationError — email_confirm mismatch (code=EMAIL_CONFIRM_MISMATCH)
        """
        # Tiger-style boundary assertions (T-15-02 server-side defence)
        assert user_id > 0, "user_id must be positive"
        assert email_confirm and email_confirm.strip(), "email_confirm required"

        user = self._user_repository.get_by_id(user_id)
        if user is None:
            # Generic error — matches AuthService.login pattern (anti-enumeration)
            raise InvalidCredentialsError()

        # Case-insensitive match per UI-SPEC §190 + CONTEXT D-RES locked
        if email_confirm.strip().lower() != user.email.lower():
            raise ValidationError(
                message="Confirmation email does not match",
                code="EMAIL_CONFIRM_MISMATCH",
                user_message="Confirmation email does not match",
            )

        # Step 1: tasks (SET NULL FK) + uploaded files. Reuses SCOPE-05 path
        # which commits internally — that's fine; steps are independent.
        counts = self.delete_user_data(user_id)

        # Step 2: rate_limit_buckets (no FK; prefix-match avoids ip:* keys).
        # Pattern locked: 'user:<uid>:%' — matches user:42:hour, user:42:concurrent,
        # user:42:tx:hour, user:42:audio_min:day. NEVER matches ip:10.0.0.0/24:*.
        bucket_count = self.session.execute(
            text(
                "DELETE FROM rate_limit_buckets WHERE bucket_key LIKE :pattern"
            ),
            {"pattern": f"user:{user_id}:%"},
        ).rowcount or 0

        # Step 3: user row → ORM CASCADE fires for the 4 CASCADE FKs.
        # PRAGMA foreign_keys=ON enforced globally (Phase 10-04).
        deleted = self._user_repository.delete(user_id)
        if not deleted:
            # Race-defensive: another delete won. Treat as user-not-found.
            raise InvalidCredentialsError()
        self.session.commit()

        # Logging discipline (AUTH-09 + T-13-13): user_id only, never email.
        logger.info(
            "Account deleted user_id=%s tasks=%s files=%s buckets=%s",
            user_id, counts["tasks_deleted"], counts["files_deleted"], bucket_count,
        )
        return {**counts, "rate_limit_buckets_deleted": bucket_count}
    ```

    Tiger-style: assertions at boundary (user_id > 0, email_confirm non-empty); fail-loud on each unhappy branch.
    SRP: service owns business logic + cascade order; route does HTTP only.
    DRY: reuses `delete_user_data` for tasks + files (SCOPE-05 path); no duplication.
    No nested-if: each guard is a flat early-raise.
    Naming: `email_confirm` (not `confirm` / `e2`); `bucket_count` (not `bc` / `n`).
    Anti-pattern avoided: no `session.delete(user)` before tasks deleted (Pitfall 2 — would IntegrityError on tasks.user_id NOT NULL).

    Do NOT bump token_version on delete (T-15-03 LOCKED — user-row-gone is the invalidation signal; cookie clearing in route is the UX clean-up).
  </action>
  <verify>
    <automated>python -c "from app.services.account_service import AccountService; import inspect; assert 'delete_account' in dir(AccountService); sig = inspect.signature(AccountService.delete_account); print(sig)"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def delete_account" app/services/account_service.py` returns 1
    - `grep -c "DELETE FROM rate_limit_buckets WHERE bucket_key LIKE" app/services/account_service.py` returns 1
    - `grep -c "self.delete_user_data(user_id)" app/services/account_service.py` returns 1 (Step 1 reuse)
    - `grep -c "self._user_repository.delete(user_id)" app/services/account_service.py` returns 1 (Step 3)
    - `grep -c "EMAIL_CONFIRM_MISMATCH" app/services/account_service.py` returns 1
    - `grep -c "assert user_id > 0" app/services/account_service.py` >= 2 (get_account_summary + delete_account)
    - `grep -c "assert email_confirm" app/services/account_service.py` returns 1
    - `grep -cE "^\s+if .*\bif\b" app/services/account_service.py` returns 0
    - `python -c "from app.services.account_service import AccountService"` exits 0
    - Existing /data tests still pass: `pytest tests/integration/test_account_routes.py -k delete_user_data -q`
  </acceptance_criteria>
  <done>delete_account method exists with correct cascade order; reuses delete_user_data; rate_limit_buckets prefix-match; case-insensitive email; no token_version bump; backward compat preserved.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add DELETE /api/account route + extend get_account_service factory if needed</name>
  <files>app/api/account_routes.py</files>
  <read_first>
    - app/api/account_routes.py (full — verify post-Plan 15-03 state with /me route + AccountSummaryResponse import; confirm existing get_account_service factory wiring)
    - app/api/dependencies.py (get_account_service, get_authenticated_user, get_db_session)
    - app/api/schemas/account_schemas.py (DeleteAccountRequest from Plan 15-01)
    - app/api/_cookie_helpers.py (clear_auth_cookies from Plan 15-01)
    - app/api/exception_handlers.py (validation_error_handler — IMPORTANT: read this to confirm what HTTP status ValidationError maps to. CONTEXT D-RES says 400; if handler defaults to 422 the route must wrap in HTTPException(400) explicitly. PATTERNS.md §"Anti-enumeration generic errors" flags this.)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"app/api/account_routes.py" — DELETE route template
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Backend: New Routes" §915-925
  </read_first>
  <behavior>
    - DELETE /api/account with body {email_confirm: 'matching@email.com'} → 204 + Set-Cookie deletions for session + csrf_token.
    - DELETE /api/account with body {email_confirm: 'wrong@email.com'} → 400 (or 422 — confirm via exception_handler reading) with body containing `EMAIL_CONFIRM_MISMATCH` code.
    - DELETE /api/account anonymous → 401.
    - DELETE /api/account with no body → 422 (Pydantic validation).
  </behavior>
  <action>
    Per RESEARCH §"Cookie-Clearing Route Returns Brand-New Response" (Pattern 1) + T-15-04 mitigation: build new Response(204), call clear_auth_cookies on it, return.

    **Read exception_handlers.py FIRST.** If `validation_error_handler` maps ValidationError → 400, the route just lets it propagate. If it maps to 422, decide between two locked options:
    - Option A: change handler to 400 globally (impact other ValidationError sites — RESEARCH §1252 explicitly flags this trade-off)
    - Option B: catch ValidationError in the route and re-raise as `HTTPException(400, detail=...)` to preserve the locked CONTEXT §49 + RESEARCH §1144 contract.

    Locked recommendation: Option B (route-local) — keeps the existing handler behavior intact for register/login flows; surface DELETE /api/account 400 explicitly for the locked contract.

    Modify `app/api/account_routes.py`:

    1. Add imports at file head:
    ```python
    from fastapi import HTTPException
    from app.api._cookie_helpers import clear_auth_cookies
    from app.api.schemas.account_schemas import (
        AccountSummaryResponse,            # already from Plan 15-03
        DeleteAccountRequest,
    )
    from app.core.exceptions import ValidationError
    ```

    2. Add the DELETE route after the existing GET /me route. Empty path string `""` maps to the router prefix root → `DELETE /api/account` (verify with FastAPI; alternative `"/"` is also valid):
    ```python
    @account_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_account(
        body: DeleteAccountRequest,
        user: User = Depends(get_authenticated_user),
        account_service: AccountService = Depends(get_account_service),
    ) -> Response:
        """DELETE /api/account — cascade delete + clear cookies. SCOPE-06.

        Body: {email_confirm: EmailStr} — case-insensitive match against
        request.state.user.email enforced by AccountService.delete_account.

        Mismatched email → 400 EMAIL_CONFIRM_MISMATCH (locked contract per
        CONTEXT §49). Service-layer ValidationError is re-raised as 400 here
        rather than letting it surface as the global handler's 422 — this is
        intentional and route-local; other ValidationError sites unaffected.
        """
        try:
            account_service.delete_account(int(user.id), body.email_confirm)
        except ValidationError as exc:
            # Locked: 400 with generic copy + structured code (T-15-05 anti-enum)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "message": exc.user_message,
                        "code": exc.code,
                    }
                },
            )

        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response
    ```

    Tiger-style: route catches the documented business exception only; InvalidCredentialsError continues to propagate to existing 401 handler (correct behavior).
    SRP: route handles HTTP boundary translation only; cascade logic in service.
    No nested-if: one flat try/except, then return.
    T-15-04 mitigation explicit: build NEW Response, call clear_auth_cookies on it. NEVER `Depends(Response)` + `return Response(...)`.

    If the existing `get_account_service` factory in `app/api/dependencies.py` does NOT inject `user_repository` — that's fine. Plan 15-03 made AccountService.__init__ lazy-construct from session. Verify the factory signature, do NOT modify unless DI override required by test fixtures forces it. Tests use `account_app` fixture with Container override; the per-route Depends still resolves through Plan 15-03's session-only factory.
  </action>
  <verify>
    <automated>python -c "from app.api.account_routes import account_router; routes = [(r.methods, r.path) for r in account_router.routes if hasattr(r, 'methods')]; print(routes); assert any('DELETE' in m and p in ('', '/') for m,p in routes)"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -cE "@account_router\\.delete\\(\"(/?)?\"" app/api/account_routes.py` returns 2 (existing /data + new "")
    - `grep -c "body: DeleteAccountRequest" app/api/account_routes.py` returns 1
    - `grep -c "clear_auth_cookies(response)" app/api/account_routes.py` returns 1
    - `grep -c "Depends(Response)" app/api/account_routes.py` returns 0 (T-15-04 anti-pattern absent)
    - `grep -cE "^\s+if .*\bif\b" app/api/account_routes.py` returns 0
    - Module imports cleanly: `python -c "from app.api.account_routes import account_router"` exits 0
    - Route registration confirmed via the verify command above
  </acceptance_criteria>
  <done>DELETE /api/account route registered; ValidationError translated to 400; cookies cleared on success via fresh Response.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: 7 integration tests covering cascade, email-mismatch, case-insensitive, cookies, auth, cross-user, no-body</name>
  <files>tests/integration/test_account_routes.py</files>
  <read_first>
    - tests/integration/test_account_routes.py (full — fixture stack + _register helper at lines 55-117 + cross-user pattern at lines 228-260)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"tests/integration/test_account_routes.py (extend)" — `_seed_full_user_universe` helper plus 8 test names from RESEARCH §1055-1064
    - app/infrastructure/database/models.py (column names for INSERT stmts: api_keys, subscriptions, usage_events, device_fingerprints, rate_limit_buckets — required by `_seed_full_user_universe`)
    - app/services/free_tier_gate.py lines 75-90 + 170-220 (bucket_key naming `user:<uid>:hour` style — required by the rate_limit_buckets seed)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Test Patterns/Backend Integration Tests" §1046-1064
  </read_first>
  <behavior>
    See acceptance_criteria — 7 specific test cases enumerated.
  </behavior>
  <action>
    Extend `tests/integration/test_account_routes.py` with a seed helper + 7 tests. Use existing fixtures (`client`, `session_factory`, `account_app`, `_register`).

    **3a. Add helper near other helpers (after `_insert_task` at lines ~120-150):**
    ```python
    def _seed_full_user_universe(session_factory, *, user_id: int) -> None:
        """Seed one row per dependent table for cascade tests.

        Tables: tasks, api_keys, subscriptions, usage_events,
        device_fingerprints, rate_limit_buckets. Uses raw SQL for
        determinism — column lists locked at Phase 10/11 schema.
        """
        with session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO tasks (id, file_name, status, user_id) "
                    "VALUES (:id, :fn, 'pending', :uid)"
                ),
                {"id": f"task-{user_id}", "fn": f"f-{user_id}.wav", "uid": user_id},
            )
            session.execute(
                text(
                    "INSERT INTO api_keys (user_id, prefix, key_hash, name, created_at, last_used_at) "
                    "VALUES (:uid, :pfx, :h, 'seeded', :ts, NULL)"
                ),
                {
                    "uid": user_id,
                    "pfx": f"pfx{user_id:04d}",
                    "h": "deadbeef" * 8,
                    "ts": "2026-04-29T00:00:00+00:00",
                },
            )
            session.execute(
                text(
                    "INSERT INTO subscriptions (user_id, plan, status) "
                    "VALUES (:uid, 'pro', 'active')"
                ),
                {"uid": user_id},
            )
            session.execute(
                text(
                    "INSERT INTO usage_events (user_id, idempotency_key, gpu_seconds, file_seconds, model, created_at) "
                    "VALUES (:uid, :idk, 1, 1, 'tiny', :ts)"
                ),
                {"uid": user_id, "idk": f"seed-{user_id}", "ts": "2026-04-29T00:00:00+00:00"},
            )
            session.execute(
                text(
                    "INSERT INTO device_fingerprints (user_id, cookie_hash, ua_hash, ip_block, device_id, created_at) "
                    "VALUES (:uid, :ck, :ua, :ip, :did, :ts)"
                ),
                {
                    "uid": user_id,
                    "ck": "c" * 64,
                    "ua": "a" * 64,
                    "ip": "10.0.0.0/24",
                    "did": f"dev-{user_id}",
                    "ts": "2026-04-29T00:00:00+00:00",
                },
            )
            session.execute(
                text(
                    "INSERT INTO rate_limit_buckets (bucket_key, tokens, last_refill) "
                    "VALUES (:k, 5, :ts)"
                ),
                {"k": f"user:{user_id}:hour", "ts": "2026-04-29T00:00:00+00:00"},
            )
            session.commit()
    ```

    **NOTE:** the column lists above are best-effort matches to RESEARCH §schema notes. Plan executor MUST verify against `app/infrastructure/database/models.py` before committing. If a column name differs (e.g., `subscriptions.plan_id` vs `plan`), correct in this helper.

    **3b. Add 7 test cases (after existing tests):**

    ```python
    @pytest.mark.integration
    def test_delete_account_cascade_full_universe(client, session_factory):
        user_id = _register(client, "cascade@example.com")
        _seed_full_user_universe(session_factory, user_id=user_id)

        response = client.delete(
            "/api/account",
            json={"email_confirm": "cascade@example.com"},
        )

        assert response.status_code == 204
        with session_factory() as session:
            for table_with_fk in ("tasks", "api_keys", "subscriptions",
                                  "usage_events", "device_fingerprints"):
                count = session.execute(
                    text(f"SELECT COUNT(*) FROM {table_with_fk} WHERE user_id = :uid"),
                    {"uid": user_id},
                ).scalar_one()
                assert count == 0, f"{table_with_fk} not cascaded"
            bucket_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM rate_limit_buckets "
                    "WHERE bucket_key LIKE :pattern"
                ),
                {"pattern": f"user:{user_id}:%"},
            ).scalar_one()
            assert bucket_count == 0, "rate_limit_buckets not pre-deleted"
            user_count = session.execute(
                text("SELECT COUNT(*) FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).scalar_one()
            assert user_count == 0, "users row not deleted"


    @pytest.mark.integration
    def test_delete_account_email_mismatch_400(client, session_factory):
        user_id = _register(client, "mismatch@example.com")
        _seed_full_user_universe(session_factory, user_id=user_id)

        response = client.delete(
            "/api/account",
            json={"email_confirm": "different@example.com"},
        )

        assert response.status_code == 400
        body = response.json()
        # locked anti-enum copy + structured code
        detail = body.get("detail", body)
        # Either nested error.code or detail.error.code depending on handler
        flattened = str(detail)
        assert "EMAIL_CONFIRM_MISMATCH" in flattened
        # Data preserved on mismatch
        with session_factory() as session:
            user_count = session.execute(
                text("SELECT COUNT(*) FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).scalar_one()
            assert user_count == 1
            task_count = session.execute(
                text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
                {"uid": user_id},
            ).scalar_one()
            assert task_count == 1


    @pytest.mark.integration
    def test_delete_account_email_case_insensitive(client, session_factory):
        user_id = _register(client, "case@example.com")
        _seed_full_user_universe(session_factory, user_id=user_id)

        response = client.delete(
            "/api/account",
            json={"email_confirm": "CASE@Example.COM"},
        )

        assert response.status_code == 204
        with session_factory() as session:
            user_count = session.execute(
                text("SELECT COUNT(*) FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).scalar_one()
            assert user_count == 0


    @pytest.mark.integration
    def test_delete_account_clears_cookies(client):
        _register(client, "cookies@example.com")

        response = client.delete(
            "/api/account",
            json={"email_confirm": "cookies@example.com"},
        )

        assert response.status_code == 204
        set_cookie_headers = response.headers.get_list("set-cookie")
        joined = "\n".join(set_cookie_headers).lower()
        assert "session=" in joined
        assert "csrf_token=" in joined
        assert joined.count("max-age=0") == 2


    @pytest.mark.integration
    def test_delete_account_requires_auth(account_app):
        from fastapi.testclient import TestClient
        app, _ = account_app
        anon = TestClient(app)

        response = anon.delete(
            "/api/account",
            json={"email_confirm": "noone@example.com"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"


    @pytest.mark.integration
    def test_delete_account_preserves_other_user_data(account_app, session_factory):
        from fastapi.testclient import TestClient
        app, _ = account_app

        alice_client = TestClient(app)
        alice_id = _register(alice_client, "alice-iso@example.com")
        _seed_full_user_universe(session_factory, user_id=alice_id)

        bob_client = TestClient(app)
        bob_id = _register(bob_client, "bob-iso@example.com")
        _seed_full_user_universe(session_factory, user_id=bob_id)

        response = alice_client.delete(
            "/api/account",
            json={"email_confirm": "alice-iso@example.com"},
        )
        assert response.status_code == 204

        # Bob untouched
        with session_factory() as session:
            for table in ("tasks", "api_keys", "subscriptions",
                          "usage_events", "device_fingerprints"):
                count = session.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"),
                    {"uid": bob_id},
                ).scalar_one()
                assert count == 1, f"Bob lost data in {table}"
            bob_buckets = session.execute(
                text(
                    "SELECT COUNT(*) FROM rate_limit_buckets "
                    "WHERE bucket_key LIKE :pattern"
                ),
                {"pattern": f"user:{bob_id}:%"},
            ).scalar_one()
            assert bob_buckets == 1


    @pytest.mark.integration
    def test_delete_account_no_body_returns_422(client):
        _register(client, "nobody@example.com")

        response = client.delete("/api/account")

        # Pydantic body validation — 422 with field-required for email_confirm
        assert response.status_code == 422
    ```

    Naming locked per CLAUDE.md self-explanatory: `user_id` (not `uid` in test scope), `bob_buckets` (not `bb`), `set_cookie_headers` (not `sch`).
    Tiger-style: each assertion has a message on the cascade test (`f"{table_with_fk} not cascaded"`).
    No nested-if: one assertion per fact; loops use simple `for` without inner branching.
  </action>
  <verify>
    <automated>pytest tests/integration/test_account_routes.py -k "delete_account" -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/integration/test_account_routes.py -k "delete_account_cascade_full_universe" -q` shows 1 passing
    - `pytest tests/integration/test_account_routes.py -k "delete_account_email_mismatch_400" -q` shows 1 passing
    - `pytest tests/integration/test_account_routes.py -k "delete_account_email_case_insensitive" -q` shows 1 passing
    - `pytest tests/integration/test_account_routes.py -k "delete_account_clears_cookies" -q` shows 1 passing
    - `pytest tests/integration/test_account_routes.py -k "delete_account_requires_auth" -q` shows 1 passing
    - `pytest tests/integration/test_account_routes.py -k "delete_account_preserves_other_user_data" -q` shows 1 passing
    - `pytest tests/integration/test_account_routes.py -k "delete_account_no_body_returns_422" -q` shows 1 passing
    - All 7 new tests pass in single command: `pytest tests/integration/test_account_routes.py -k "delete_account" -q` reports >= 7 passing
    - All existing /data + /me tests still pass (no regression):
      `pytest tests/integration/test_account_routes.py -q` shows zero failures
    - `grep -cE "^\s+if .*\bif\b" tests/integration/test_account_routes.py` returns 0 (test code respects the rule too)
  </acceptance_criteria>
  <done>7 cascade/auth/isolation tests green; helper covers all 6 dependent tables; cross-user isolation smoke verified; no regressions.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → DualAuthMiddleware → DELETE /api/account | Cookie session + CSRF token verified before route entry (MID-04) |
| Service → multiple DB tables in 3 steps | Step 1 commits internally; Step 2+3 commit at user-row delete; per-step atomicity |
| User row delete → ORM CASCADE → 4 dependent tables | PRAGMA foreign_keys=ON enforced (Phase 10-04 boot assertion) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-15-01 | Tampering / Information Disclosure | Cascade race — concurrent reads observe orphan rows | mitigate | Step ordering locked: tasks first, buckets second, user last; commits at each step boundary; middleware lookup of deleted user 401s on next request |
| T-15-02 | Tampering | CSRF replay or compromised cookie deletes account silently | mitigate | (a) CSRF middleware requires X-CSRF-Token (MID-04 existing); (b) service re-validates email_confirm == user.email case-insensitive; (c) UI gates submit button (Plan 15-06) — defence-in-depth |
| T-15-03 | Information Disclosure | Zombie session post-delete | accept | User row deleted → middleware get_by_id returns None → 401 on next request. No token_version bump needed (cookie cleared in response for clean UX) |
| T-15-04 | Information Disclosure | Cookie-deletion headers dropped | mitigate | Build NEW Response(204), call clear_auth_cookies on it; verifier-grep `Depends(Response)` returns 0 |
| T-15-05 | Information Disclosure | Email enumeration via 400 vs 401 | mitigate | 400 EMAIL_CONFIRM_MISMATCH only reachable AFTER auth passed; identical body structure across mismatch cases (`Confirmation email does not match` / `EMAIL_CONFIRM_MISMATCH`); 401 fully separate code path |
| T-15-06 | Tampering | rate_limit_buckets retained → next user with reused id inherits exhaustion | mitigate | DELETE WHERE bucket_key LIKE 'user:<uid>:%' (string prefix); test_delete_account_cascade_full_universe asserts COUNT=0 |
| T-15-11 | Information Disclosure | Email leaked in service logs | mitigate | logger.info uses `user_id=%s` only — verifier-grep `logger.*user\.email` returns 0 in account_service.py |
| Pitfall 2 | Tampering / DoS | tasks.user_id NOT NULL violation if user deleted before tasks | mitigate | Step 1 (delete_user_data) DELETEs tasks before Step 3 user delete; cascade test exercises this exact scenario |
| Pitfall 3 | Tampering | rate_limit_buckets orphaned (no FK) | mitigate | Step 2 explicit prefix-match DELETE; cross-user test confirms scope correctness |
</threat_model>

<verification>
- All 7 delete_account tests pass via `pytest tests/integration/test_account_routes.py -k delete_account -x -q`
- All existing /data + /me + logout tests still pass (zero regression):
  `pytest tests/integration/test_account_routes.py tests/integration/test_auth_routes.py -q`
- Verifier greps pass: nested-if = 0, Depends(Response) = 0, logger.email = 0
- T-15-04 explicit: only one place builds Response in the route (single grep match)
- Cross-user isolation: Bob's data fully intact after Alice's delete — covered by test_delete_account_preserves_other_user_data
</verification>

<success_criteria>
1. DELETE /api/account cascades to all 6 dependent tables in Strategy C order (tasks → buckets → user→ORM CASCADE for 4)
2. Email mismatch returns 400 with EMAIL_CONFIRM_MISMATCH code, data preserved
3. Case-insensitive email match works (FOO@Example.com == foo@example.com)
4. Success response clears session + csrf_token cookies (Max-Age=0)
5. Anonymous DELETE returns 401 "Authentication required"
6. Other users' data is untouched (cross-user isolation smoke)
7. Empty body returns 422 (Pydantic validation)
</success_criteria>

<output>
After completion, create `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-04-SUMMARY.md`
</output>
