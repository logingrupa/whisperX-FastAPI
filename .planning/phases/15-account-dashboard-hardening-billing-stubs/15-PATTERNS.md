# Phase 15: Account Dashboard Hardening + Billing Stubs - Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 26 (12 backend + 14 frontend) — all with strong analogs in repo.
**Analogs found:** 26 / 26 (100%)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/api/_cookie_helpers.py` | utility | request-response | `app/api/auth_routes.py:101-104` (`_clear_auth_cookies`) | exact (extract) |
| `app/api/schemas/account_schemas.py` | model (Pydantic DTO) | request-response | `app/api/schemas/auth_schemas.py` | exact |
| `app/api/account_routes.py` (modify) | controller | request-response (CRUD) | `app/api/account_routes.py:34-41` (existing `/data`) + `app/api/key_routes.py:75-88` | exact |
| `app/api/auth_routes.py` (modify, +/logout-all) | controller | request-response | `app/api/auth_routes.py:182-194` (`/logout`) | exact |
| `app/services/account_service.py` (modify) | service | CRUD | `app/services/account_service.py:29-43` (`delete_user_data`) + `app/services/auth/auth_service.py:91-97` (`logout_all_devices`) | exact |
| `app/core/container.py` (modify) | config (DI) | n/a | `container.py:130-135` (`auth_service` factory) | exact |
| `app/api/dependencies.py` (modify, optional) | utility (DI) | n/a | `dependencies.py:223-241` (`get_auth_service`, `get_key_service`) | exact |
| `tests/integration/test_account_routes.py` (extend) | test | request-response | `tests/integration/test_account_routes.py:55-117` (fixtures) + body cases at `:150-272` | exact |
| `tests/integration/test_auth_routes.py` (extend) | test | request-response | `tests/integration/test_auth_routes.py:271-291` (logout tests) | exact |
| `tests/integration/test_logout_all.py` (NEW, optional split) | test | request-response | `tests/integration/test_auth_routes.py:271-291` | role-match |
| `tests/unit/api/test_cookie_helpers.py` (NEW) | test | n/a | `tests/integration/test_auth_routes.py:271-283` | role-match |
| `frontend/src/lib/api/accountApi.ts` | service (HTTP wrapper) | request-response | `frontend/src/lib/api/keysApi.ts` | exact |
| `frontend/src/lib/apiClient.ts` (modify) | service (HTTP) | request-response | `apiClient.ts:155-166` (existing exports object) | exact (in-place extend) |
| `frontend/src/lib/stores/authStore.ts` (modify) | store | event-driven | `authStore.ts:74-113` (existing create + login/register/logout) | exact |
| `frontend/src/routes/AccountPage.tsx` | component (page) | request-response | `frontend/src/routes/KeysDashboardPage.tsx` | exact |
| `frontend/src/routes/AppRouter.tsx` (modify) | controller (router) | n/a | `AppRouter.tsx:7,52` (current `AccountStubPage` mount) | exact |
| `frontend/src/routes/RequireAuth.tsx` (modify) | component (gate) | n/a | `RequireAuth.tsx:12-22` (current gate) | exact |
| `frontend/src/components/dashboard/UpgradeInterestDialog.tsx` | component (dialog) | request-response | `frontend/src/components/dashboard/CreateKeyDialog.tsx` | role-match (form pattern) |
| `frontend/src/components/dashboard/DeleteAccountDialog.tsx` | component (dialog) | request-response | `frontend/src/components/dashboard/CreateKeyDialog.tsx` (form/match-gate) + `RevokeKeyDialog.tsx` (destructive action) | exact (composite) |
| `frontend/src/components/dashboard/LogoutAllDialog.tsx` | component (dialog) | request-response | `frontend/src/components/dashboard/RevokeKeyDialog.tsx` | exact |
| `frontend/src/tests/msw/account.handlers.ts` | test (mock) | request-response | `frontend/src/tests/msw/keys.handlers.ts` + `auth.handlers.ts` | exact |
| `frontend/src/tests/msw/handlers.ts` (modify) | test (barrel) | n/a | `handlers.ts:1-12` (current barrel) | exact |
| `frontend/src/tests/routes/AccountPage.test.tsx` | test | request-response | `frontend/src/tests/routes/KeysDashboardPage.test.tsx` | exact |
| `frontend/src/tests/components/DeleteAccountDialog.test.tsx` | test | request-response | `frontend/src/tests/routes/KeysDashboardPage.test.tsx` (revoke flow §86-100) | role-match |
| `frontend/src/tests/components/LogoutAllDialog.test.tsx` | test | request-response | `frontend/src/tests/routes/KeysDashboardPage.test.tsx` (revoke flow) | role-match |
| `frontend/src/tests/components/UpgradeInterestDialog.test.tsx` | test | request-response | `frontend/src/tests/routes/KeysDashboardPage.test.tsx` (create flow §49-66) | role-match |
| `frontend/src/tests/lib/stores/authStore.test.ts` (extend) | test | event-driven | `frontend/src/tests/lib/stores/authStore.test.ts` (existing) | exact |
| `frontend/src/tests/lib/apiClient.test.ts` (extend) | test | request-response | `apiClient.test.ts:69-80` (existing suppress401Redirect for POST) | exact |

---

## Pattern Assignments

### `app/api/_cookie_helpers.py` (utility, NEW)

**Analog:** `app/api/auth_routes.py:52-104`

**Goal:** extract `_clear_auth_cookies` (and optionally `_set_auth_cookies` constants) so both `auth_routes.py` and `account_routes.py` import the single source. DRY locked at CONTEXT §72.

**Imports + constants pattern** (`auth_routes.py:32-53`):
```python
from __future__ import annotations
from fastapi import Response

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"
```

**Helper to copy verbatim** (`auth_routes.py:101-104`):
```python
def clear_auth_cookies(response: Response) -> None:
    """Clear both session and csrf cookies (used by logout, logout-all, delete-account)."""
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
```

After extraction, replace the private `_clear_auth_cookies` callsite at `auth_routes.py:193` with `clear_auth_cookies(response)` and import from `app.api._cookie_helpers`.

---

### `app/api/schemas/account_schemas.py` (model, NEW)

**Analog:** `app/api/schemas/auth_schemas.py:1-44`

**Imports pattern** (lines 1-10):
```python
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
```

**BaseModel + EmailStr + Field pattern** (lines 13-24):
```python
class RegisterRequest(BaseModel):
    """POST /auth/register body."""
    email: EmailStr = Field(..., description="User email (unique identifier)")
    password: str = Field(..., min_length=8, max_length=128, description="...")
```

**Phase 15 schemas to write** (RESEARCH §551-572):
```python
class AccountSummaryResponse(BaseModel):
    """GET /api/account/me — server-side hydration source-of-truth."""
    user_id: int
    email: EmailStr
    plan_tier: str = Field(..., description="One of free|trial|pro|team")
    trial_started_at: datetime | None = None
    token_version: int = Field(..., description="For cross-tab refresh debounce")


class DeleteAccountRequest(BaseModel):
    """DELETE /api/account body. email_confirm validated against user.email."""
    email_confirm: EmailStr = Field(...)
```

`datetime` import from `from datetime import datetime` — no other changes from auth_schemas pattern.

---

### `app/api/account_routes.py` (controller, MODIFY: add /me + DELETE)

**Analog (existing in same file):** `app/api/account_routes.py:24-41`

**Imports pattern** (lines 1-22 — extend with new imports):
```python
from fastapi import APIRouter, Depends, Response, status
from app.api.dependencies import get_authenticated_user, get_db_session
from app.domain.entities.user import User
from app.services.account_service import AccountService
```

**Add for Phase 15:**
```python
from app.api._cookie_helpers import clear_auth_cookies
from app.api.schemas.account_schemas import AccountSummaryResponse, DeleteAccountRequest
```

**Existing route to mirror** (lines 34-41):
```python
@account_router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_data(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    """Delete the caller's tasks + uploaded files. User row preserved."""
    account_service.delete_user_data(int(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

**New routes to add (RESEARCH §905-925):**
```python
@account_router.get("/me", response_model=AccountSummaryResponse)
async def get_account_me(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> AccountSummaryResponse:
    summary = account_service.get_account_summary(int(user.id))
    return AccountSummaryResponse(**summary)


@account_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    account_service.delete_account(int(user.id), body.email_confirm)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)  # imported from _cookie_helpers
    return response
```

**Cookie-deletion anti-pattern (T-15-04, RESEARCH §299, auth_routes.py:182-194):** must build a new `Response(status_code=204)` and call helper on it. NEVER use `response: Response = Depends(...)` and `return Response(...)` — Set-Cookie headers are dropped.

**404 path (cross-user matrix):** deferred to Phase 16 per CONTEXT §37; do NOT add 404 logic here.

---

### `app/api/auth_routes.py` (controller, MODIFY: add /logout-all)

**Analog (existing in same file):** `app/api/auth_routes.py:182-194` (logout)

**Existing logout pattern to mirror** (lines 182-194):
```python
@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response
```

**New route to add (RESEARCH §930-940):**
```python
from app.api.dependencies import get_auth_service, get_authenticated_user
# clear_auth_cookies imported from app.api._cookie_helpers

@auth_router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    user: User = Depends(get_authenticated_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """POST /auth/logout-all — bump token_version + clear cookies. AUTH-06."""
    auth_service.logout_all_devices(int(user.id))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response
```

`AuthService.logout_all_devices` (`app/services/auth/auth_service.py:91-97`) already exists; route is glue only.

Side effect: replace local `_clear_auth_cookies` def at line 101-104 with `from app.api._cookie_helpers import clear_auth_cookies` (DRY — single source).

---

### `app/services/account_service.py` (service, MODIFY: +delete_account, +get_account_summary)

**Analog (in same file):** `app/services/account_service.py:29-43` (`delete_user_data`)

**Existing constructor + method pattern** (lines 20-43):
```python
class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def delete_user_data(self, user_id: int) -> dict[str, int]:
        file_names = self._collect_user_file_names(user_id)
        tasks_deleted = self._delete_tasks_for_user(user_id)
        files_deleted = self._delete_files(file_names)
        logger.info("Account data deleted user_id=%s tasks=%s files=%s",
                    user_id, tasks_deleted, files_deleted)
        return {"tasks_deleted": tasks_deleted, "files_deleted": files_deleted}
```

**Logout-all-style guard pattern** (`app/services/auth/auth_service.py:91-97`):
```python
def logout_all_devices(self, user_id: int) -> None:
    user = self.user_repository.get_by_id(user_id)
    if user is None:
        raise InvalidCredentialsError()
    self.user_repository.update_token_version(user_id, user.token_version + 1)
    logger.info("Logout-all-devices id=%s", user_id)
```

**Constructor extension to add (RESEARCH §899):**
```python
def __init__(
    self,
    session: Session,
    user_repository: IUserRepository | None = None,
) -> None:
    self.session = session
    # Lazy-construct from session if not injected — preserves SCOPE-05 callers
    self._user_repository = user_repository or SQLAlchemyUserRepository(session)
```

**`delete_account` to add (RESEARCH §836-881):** raw `text()` SQL pattern already used in this file at lines 47-49 (parameterized `:uid` binding). Reuse:
```python
def delete_account(self, user_id: int, email_confirm: str) -> dict[str, int]:
    assert user_id > 0, "user_id must be positive"            # tiger-style boundary
    assert email_confirm and email_confirm.strip(), "email_confirm required"

    user = self._user_repository.get_by_id(user_id)
    if user is None:
        raise InvalidCredentialsError()
    if email_confirm.strip().lower() != user.email.lower():
        raise ValidationError(
            message="Confirmation email does not match",
            code="EMAIL_CONFIRM_MISMATCH",
            user_message="Confirmation email does not match",
        )
    counts = self.delete_user_data(user_id)            # Step 1
    bucket_count = self.session.execute(               # Step 2
        text("DELETE FROM rate_limit_buckets WHERE bucket_key LIKE :pattern"),
        {"pattern": f"user:{user_id}:%"},
    ).rowcount or 0
    deleted = self._user_repository.delete(user_id)    # Step 3 → CASCADE
    if not deleted:
        raise InvalidCredentialsError()
    self.session.commit()
    logger.info("Account deleted user_id=%s tasks=%s files=%s buckets=%s",
                user_id, counts["tasks_deleted"], counts["files_deleted"], bucket_count)
    return {**counts, "rate_limit_buckets_deleted": bucket_count}
```

**`get_account_summary` to add:** pure read; mirrors logout-all-devices guard (RESEARCH §884-896):
```python
def get_account_summary(self, user_id: int) -> dict:
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

**Imports to add at file head:**
```python
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
```

---

### `app/domain/repositories/user_repository.py` (verification only)

`delete(identifier: int) -> bool` already declared at lines 80-89. SQLAlchemy impl at `sqlalchemy_user_repository.py:122-137` does `session.delete(orm_user)` + `commit` — fires FK CASCADE on api_keys/subscriptions/usage_events/device_fingerprints. No change required.

**Pitfall:** `tasks.user_id` is `ondelete="SET NULL"` (`models.py:142`). SET NULL fires before user-row delete, but `tasks.user_id` was made NOT NULL in migration 0003 → IntegrityError unless tasks pre-deleted via `delete_user_data`. Order in `delete_account` is therefore mandatory: `delete_user_data → DELETE rate_limit_buckets → user_repository.delete`.

---

### `app/core/container.py` (modify, OPTIONAL)

**Analog:** `container.py:104-107` (user_repository factory) + `container.py:130-135` (auth_service factory)

If a Container-level `account_service` provider is desired (cleaner than the per-route `get_account_service` factory at `account_routes.py:27-31`):
```python
account_service = providers.Factory(
    AccountService,
    session=db_session_factory,
    user_repository=user_repository,
)
```

**Decision (CONTEXT §125):** existing `account_routes.py:27-31` `get_account_service` factory is fine — extend it to accept user_repository if needed, OR just lazy-construct inside `AccountService.__init__` (RESEARCH §899 preferred). No mandatory container change.

---

### `tests/integration/test_account_routes.py` (extend)

**Analog (in same file):** `tests/integration/test_account_routes.py:1-272` — already covers `/data` route with full fixture stack.

**Reusable fixtures** (lines 55-117):
```python
@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str: ...                  # creates SQLite + tables
@pytest.fixture
def session_factory(tmp_db_url): ...                        # sessionmaker
@pytest.fixture
def upload_dirs(tmp_path, monkeypatch) -> tuple[Path, Path]: ...
@pytest.fixture
def account_app(tmp_db_url, session_factory): ...           # slim FastAPI w/ DualAuth
@pytest.fixture
def client(account_app): ...                                # TestClient

def _register(client: TestClient, email: str, password: str = "supersecret123") -> int: ...
def _insert_task(session_factory, *, user_id, file_name) -> int: ...
```

**Test pattern to mirror** (lines 150-174 — `test_delete_user_data_removes_tasks`):
```python
@pytest.mark.integration
def test_delete_user_data_removes_tasks(client, session_factory, upload_dirs):
    user_id = _register(client, "alice@example.com")
    for index in range(3):
        _insert_task(session_factory, user_id=user_id, file_name=None)
    with session_factory() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert count == 3
    response = client.delete("/api/account/data")
    assert response.status_code == 204
    with session_factory() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert count == 0
```

**Cross-user isolation pattern** (lines 228-260) → reuse for `test_delete_account_preserves_other_user_data`.

**Auth-required pattern** (lines 263-272):
```python
@pytest.mark.integration
def test_delete_user_data_requires_auth(account_app):
    app, _ = account_app
    client_no_auth = TestClient(app)
    response = client_no_auth.delete("/api/account/data")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
```

**New tests to add (RESEARCH §1055-1064):** test_get_account_me_returns_summary, test_get_account_me_requires_auth, test_delete_account_cascade_full_universe, test_delete_account_email_mismatch_400, test_delete_account_email_case_insensitive, test_delete_account_clears_cookies, test_delete_account_requires_auth, test_delete_account_preserves_other_user_data.

**Helper to add: `_seed_full_user_universe(session_factory, user_id)`** — INSERTs one row each into tasks, api_keys, subscriptions, usage_events, device_fingerprints, rate_limit_buckets (`bucket_key=f"user:{user_id}:hour"`).

**ValidationError shape assertion (anti-enum):** mirror `test_register_duplicate_email_generic_error` pattern at `test_auth_routes.py:129-142`:
```python
assert response.status_code == 400
body = response.json()
assert body["error"]["code"] == "EMAIL_CONFIRM_MISMATCH"
assert body["error"]["message"] == "Confirmation email does not match"
```

---

### `tests/integration/test_auth_routes.py` (extend, +/logout-all)

**Analog (in same file):** `test_auth_routes.py:271-291` (logout tests)

**Logout cookie-clearing pattern to mirror** (lines 271-283):
```python
@pytest.mark.integration
def test_logout_clears_cookies(client: TestClient) -> None:
    payload = {"email": "gina@example.com", "password": "supersecret123"}
    register = client.post("/auth/register", json=payload)
    assert register.status_code == 201
    response = client.post("/auth/logout")
    assert response.status_code == 204
    set_cookie_headers = response.headers.get_list("set-cookie")
    joined = "\n".join(set_cookie_headers).lower()
    assert "session=" in joined
    assert "csrf_token=" in joined
    assert "max-age=0" in joined
```

**Note:** `auth_app` fixture at lines 63-97 does NOT mount `DualAuthMiddleware` — only the slim `account_app` fixture (in test_account_routes.py:88-111) does. `/logout-all` requires auth → tests for it MUST use the `account_app` fixture or extend `auth_app` to mount DualAuthMiddleware. **Locked recommendation:** add logout-all tests to `test_account_routes.py` (already has DualAuthMiddleware wired) OR mount middleware in auth_app fixture.

**Token-version invalidation test (RESEARCH §1057):**
```python
def test_logout_all_bumps_token_version(client, session_factory):
    user_id = _register(client, "alice@example.com")
    with session_factory() as session:
        v_before = session.execute(
            text("SELECT token_version FROM users WHERE id=:uid"), {"uid": user_id}
        ).scalar_one()
    response = client.post("/auth/logout-all")
    assert response.status_code == 204
    with session_factory() as session:
        v_after = session.execute(
            text("SELECT token_version FROM users WHERE id=:uid"), {"uid": user_id}
        ).scalar_one()
    assert v_after == v_before + 1
```

---

### `tests/unit/api/test_cookie_helpers.py` (NEW)

**Analog:** `test_auth_routes.py:271-283` (cookie-deletion assertions)

Lightweight unit test — instantiate FastAPI Response, call helper, assert delete_cookie set both cookie names with `max-age=0`. Mirror the headers parsing pattern at lines 278-283.

---

### `frontend/src/lib/apiClient.ts` (MODIFY: extend get + delete signatures)

**Analog (in same file):** `apiClient.ts:155-166`

**Existing exports object:**
```typescript
export const apiClient = {
  get: <T>(path: string, headers?: Record<string, string>) =>
    request<T>({ method: 'GET', path, headers }),
  post: <T>(path: string, body?: unknown, opts?: { suppress401Redirect?: boolean }) =>
    request<T>({ method: 'POST', path, body, suppress401Redirect: opts?.suppress401Redirect }),
  put: <T>(path: string, body?: unknown) =>
    request<T>({ method: 'PUT', path, body }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>({ method: 'PATCH', path, body }),
  delete: <T>(path: string) =>
    request<T>({ method: 'DELETE', path }),
};
```

**Required extensions (RESEARCH §510-531):**
```typescript
get: <T>(path: string, opts?: { headers?: Record<string, string>; suppress401Redirect?: boolean }) =>
  request<T>({ method: 'GET', path, headers: opts?.headers, suppress401Redirect: opts?.suppress401Redirect }),
delete: <T>(path: string, body?: unknown) =>
  request<T>({ method: 'DELETE', path, body }),
```

`request()` already supports `body` on any method (`buildBody(opts)` line 74-79) and `suppress401Redirect` on any method (line 131). The only change is the public exports object.

**Caller migrations:** `keysApi.fetchKeys()` (`keysApi.ts:30-32`) doesn't pass headers — unaffected. `keysApi.revokeKey(id)` (line 38-40) doesn't pass body — unaffected.

---

### `frontend/src/lib/api/accountApi.ts` (NEW)

**Analog:** `frontend/src/lib/api/keysApi.ts` (entire file, 41 lines)

**Imports + exports pattern** (lines 1-40):
```typescript
import { apiClient } from '@/lib/apiClient';

export interface ApiKeyListItem {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  status: 'active' | 'revoked';
}

export function fetchKeys(): Promise<ApiKeyListItem[]> {
  return apiClient.get<ApiKeyListItem[]>('/api/keys');
}

export function createKey(name: string): Promise<CreatedApiKey> {
  return apiClient.post<CreatedApiKey>('/api/keys', { name });
}

export function revokeKey(id: number): Promise<void> {
  return apiClient.delete<void>(`/api/keys/${id}`);
}
```

**Phase 15 module to write (RESEARCH §577-607):**
```typescript
import { apiClient } from '@/lib/apiClient';

export interface AccountSummaryResponse {
  user_id: number;
  email: string;
  plan_tier: 'free' | 'trial' | 'pro' | 'team';
  trial_started_at: string | null;
  token_version: number;
}

export function fetchAccountSummary(): Promise<AccountSummaryResponse> {
  return apiClient.get<AccountSummaryResponse>(
    '/api/account/me',
    { suppress401Redirect: true },
  );
}

export function logoutAllDevices(): Promise<void> {
  return apiClient.post<void>('/auth/logout-all');
}

export function deleteAccount(emailConfirm: string): Promise<void> {
  return apiClient.delete<void>('/api/account', { email_confirm: emailConfirm });
}

export function submitUpgradeInterest(message: string): Promise<void> {
  return apiClient.post<void>('/billing/checkout', { plan: 'pro', message });
}
```

**501 swallow pattern (T-15-07):** caller in `UpgradeInterestDialog` catches `ApiClientError` with `statusCode === 501` and treats as success. Document in JSDoc on `submitUpgradeInterest`.

---

### `frontend/src/lib/stores/authStore.ts` (MODIFY: +refresh + isHydrating + AuthUser fields)

**Analog (in same file):** `authStore.ts:74-113`

**Existing store creation pattern:**
```typescript
export const useAuthStore = create<AuthState>((set) => {
  getChannel().addEventListener('message', (event: MessageEvent) => {
    const data = event.data as BroadcastAuthMessage;
    if (data.type === 'logout') {
      set({ user: null });
    }
  });

  return {
    user: null,
    login: async (email, password) => { /* apiClient.post -> set({user}) -> broadcast */ },
    register: async (email, password) => { /* same shape */ },
    logout: async () => { /* apiClient.post -> set({user: null}) -> broadcast */ },
  };
});
```

**Phase 15 extensions (RESEARCH §640-694):**

Extend `AuthUser` interface (lines 21-25):
```typescript
export interface AuthUser {
  id: number;
  email: string;
  planTier: string;
  trialStartedAt: string | null;
  tokenVersion: number;
}
```

Extend `AuthState` (lines 45-50):
```typescript
interface AuthState {
  user: AuthUser | null;
  isHydrating: boolean;                  // NEW — initial true
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;          // NEW
}
```

Add `refresh` method to store body:
```typescript
isHydrating: true,
refresh: async () => {
  try {
    const summary = await apiClient.get<AccountSummaryResponse>(
      '/api/account/me',
      { suppress401Redirect: true },
    );
    set({
      user: {
        id: summary.user_id,
        email: summary.email,
        planTier: summary.plan_tier,
        trialStartedAt: summary.trial_started_at,
        tokenVersion: summary.token_version,
      },
    });
  } catch (err) {
    if (!(err instanceof AuthRequiredError) && !(err instanceof ApiClientError)) {
      throw err;
    }
  } finally {
    set({ isHydrating: false });
  }
},
```

`AccountSummaryResponse` imported from `@/lib/api/accountApi`. `AuthRequiredError`, `ApiClientError` from `@/lib/apiClient`. `main.tsx` (or `App.tsx`) calls `useAuthStore.getState().refresh()` once at module load.

**Trade-off note in CLAUDE/RESEARCH:** the existing `toAuthUser(response, email)` helper (lines 65-72) only sets `id/email/planTier`. Phase 15 must extend it OR add a separate helper to populate the new fields from `/me` response. After refresh fires once, the values land. Keep `toAuthUser` minimal in login/register and let `refresh` overlay full server-state — already RESEARCH §617 locked.

---

### `frontend/src/routes/RequireAuth.tsx` (MODIFY: gate on isHydrating)

**Analog (in same file):** lines 12-22

**Existing gate:**
```typescript
export function RequireAuth() {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}
```

**Extension (RESEARCH §700-714):**
```typescript
export function RequireAuth() {
  const user = useAuthStore((s) => s.user);
  const isHydrating = useAuthStore((s) => s.isHydrating);
  const location = useLocation();

  if (isHydrating) return null;          // suppress redirect-flash during boot probe

  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}
```

No nested-if (verifier-checked: two flat guard clauses, separate predicates).

---

### `frontend/src/routes/AppRouter.tsx` (MODIFY: swap stub → AccountPage)

**Analog (in same file):** lines 7, 18-23, 47-54

**Existing import:**
```typescript
import { AccountStubPage } from './AccountStubPage';                    // line 7  → DELETE
```

**Existing lazy-load pattern (mirror for AccountPage):**
```typescript
const KeysDashboardPage = lazy(() =>
  import('./KeysDashboardPage').then((m) => ({ default: m.KeysDashboardPage })),
);
```

**Phase 15 changes:**
1. Delete `import { AccountStubPage } from './AccountStubPage';`
2. Add `const AccountPage = lazy(() => import('./AccountPage').then((m) => ({ default: m.AccountPage })));`
3. Replace line 52 `<Route path="/dashboard/account" element={<PageWrap><AccountStubPage /></PageWrap>} />` with `<Route path="/dashboard/account" element={<PageWrap><AccountPage /></PageWrap>} />`
4. Delete `frontend/src/routes/AccountStubPage.tsx`

---

### `frontend/src/routes/AccountPage.tsx` (NEW)

**Analog:** `frontend/src/routes/KeysDashboardPage.tsx` (entire file, 165 lines)

**Imports pattern** (lines 1-10):
```typescript
import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, KeyRound, Trash2 } from 'lucide-react';
import { fetchKeys, type ApiKeyListItem } from '@/lib/api/keysApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';
import { CreateKeyDialog } from '@/components/dashboard/CreateKeyDialog';
import { RevokeKeyDialog } from '@/components/dashboard/RevokeKeyDialog';
```

**Fetch + error handling pattern** (lines 23-50):
```typescript
export function KeysDashboardPage() {
  const [keys, setKeys] = useState<ApiKeyListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // ...
  const refresh = async () => {
    setError(null);
    try {
      const list = await fetchKeys();
      setKeys(list);
    } catch (err) {
      // RateLimitError BEFORE ApiClientError — RateLimitError extends ApiClientError
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
        return;
      }
      if (err instanceof ApiClientError) {
        setError('Could not load keys.');
        return;
      }
      setError('Could not load keys.');
    }
  };

  useEffect(() => { refresh(); }, []);
```

**Layout pattern (`flex flex-col gap-6`)** (line 60-79):
```tsx
return (
  <div className="flex flex-col gap-6">
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-semibold">API keys</h1>
        <p className="text-sm text-muted-foreground">
          Use these to authenticate the WhisperX HTTP API.
        </p>
      </div>
      <Button onClick={() => setCreateOpen(true)}>...</Button>
    </div>

    {error !== null && (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )}
    {/* cards / table */}
  </div>
);
```

**Dialog wiring pattern** (lines 143-161):
```tsx
<CreateKeyDialog
  open={createOpen}
  onOpenChange={setCreateOpen}
  onCreated={() => { refresh(); }}
/>
<RevokeKeyDialog
  keyId={revokeTarget?.id ?? null}
  keyName={revokeTarget?.name ?? null}
  open={revokeTarget !== null}
  onOpenChange={(o) => { if (!o) setRevokeTarget(null); }}
  onRevoked={() => { setRevokeTarget(null); refresh(); }}
/>
```

**Phase 15 page composition:** three `<Card class="p-6">` (Profile / Plan / Danger Zone — UI-SPEC §116-160) instead of header + table; same `flex flex-col gap-6 max-w-2xl mx-auto` outer container. PLAN_BADGE_VARIANT + PLAN_COPY const maps locked at UI-SPEC §107-110, §277-281. Dialog state machine identical to `createOpen` / `revokeTarget` triplet — three booleans (`upgradeOpen`, `deleteOpen`, `logoutAllOpen`).

---

### `frontend/src/components/dashboard/UpgradeInterestDialog.tsx` (NEW)

**Analog:** `frontend/src/components/dashboard/CreateKeyDialog.tsx` (entire file, 151 lines — form + submit + 429 + state machine)

**Form-state pattern** (lines 41-82):
```tsx
const [name, setName] = useState('');
const [submitting, setSubmitting] = useState(false);
const [error, setError] = useState<string | null>(null);
const [created, setCreated] = useState<CreatedApiKey | null>(null);

const onSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  if (name.trim().length === 0) {
    setError('Name is required.');
    return;
  }
  setSubmitting(true);
  setError(null);
  try {
    const apiKey = await createKey(name.trim());
    setCreated(apiKey);
  } catch (err) {
    if (err instanceof RateLimitError) {
      setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`);
    } else if (err instanceof ApiClientError) {
      setError('Could not create key.');
    } else {
      setError('Could not create key.');
    }
  } finally {
    setSubmitting(false);
  }
};
```

**Two-state DialogContent pattern** (lines 84-148): idle/form ↔ success/alert; close handler clears state. Mirror this for UpgradeInterestDialog: idle (textarea + submit) ↔ success (Alert "Thanks! Stripe ships in v1.3"). Auto-close 2s via `setTimeout(handleClose, 2000)` after success — UI-SPEC §174.

**501 swallow (T-15-07, RESEARCH §808-815):** in catch block, branch `if (err instanceof ApiClientError && err.statusCode === 501) { setSuccess(true); return; }` BEFORE the generic ApiClientError branch.

---

### `frontend/src/components/dashboard/DeleteAccountDialog.tsx` (NEW)

**Analog (composite):** `CreateKeyDialog.tsx` (form/match-gate input pattern) + `RevokeKeyDialog.tsx` (destructive variant + post-action state)

**Type-match gate pattern (RESEARCH §1014-1039 + UI-SPEC §214-227):**
```tsx
const [confirmEmail, setConfirmEmail] = useState('');
const [submitting, setSubmitting] = useState(false);
const [error, setError] = useState<string | null>(null);

const isMatched = confirmEmail.trim().toLowerCase() === userEmail.toLowerCase();

const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  if (!isMatched) return;
  setSubmitting(true);
  setError(null);
  try {
    await deleteAccount(confirmEmail);
    await logout();                 // authStore.logout()
    navigate('/login', { replace: true });
  } catch (err) {
    if (err instanceof RateLimitError) {
      setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`);
    } else if (err instanceof ApiClientError) {
      setError(err.statusCode === 400
        ? 'Confirmation email does not match.'
        : 'Could not delete account. Try again.');
    } else {
      setError('Could not delete account. Try again.');
    }
  } finally {
    setSubmitting(false);
  }
};
```

**Destructive submit-button pattern** (RevokeKeyDialog.tsx lines 85-92):
```tsx
<Button
  type="submit"
  variant="destructive"
  disabled={!isMatched || submitting}
>
  {submitting ? 'Deleting…' : 'Delete account'}
</Button>
```

**Input field pattern** (CreateKeyDialog.tsx:95-105):
```tsx
<div className="my-6 flex flex-col gap-2">
  <Label htmlFor="confirm-email">Type your email to confirm: {userEmail}</Label>
  <Input
    id="confirm-email"
    type="email"
    value={confirmEmail}
    onChange={(e) => setConfirmEmail(e.target.value)}
    autoFocus
    autoComplete="off"
    spellCheck={false}
    placeholder="you@example.com"
  />
</div>
```

`useNavigate` import: `import { useNavigate } from 'react-router-dom';`. authStore import: `const logout = useAuthStore((s) => s.logout);`.

---

### `frontend/src/components/dashboard/LogoutAllDialog.tsx` (NEW)

**Analog:** `frontend/src/components/dashboard/RevokeKeyDialog.tsx` (entire file, 98 lines — single-confirm destructive pattern)

**Full structure to mirror** (lines 21-97):
```tsx
export function RevokeKeyDialog({ keyId, keyName, open, onOpenChange, onRevoked }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = async () => {
    if (keyId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await revokeKey(keyId);
      onRevoked();
      onOpenChange(false);
    } catch (err) {
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
      } else if (err instanceof ApiClientError) {
        setError('Could not revoke key.');
      } else {
        setError('Could not revoke key.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revoke key?</DialogTitle>
          <DialogDescription>...</DialogDescription>
        </DialogHeader>
        {error !== null && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DialogFooter className="mt-4">
          <Button type="button" variant="ghost" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm} disabled={submitting}>
            {submitting ? 'Revoking…' : 'Revoke'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

**Phase 15 mapping:** rename `revokeKey` → `logoutAllDevices`; rename copy per UI-SPEC §326-333; on success call `await logout(); navigate('/login', {replace:true})` instead of `onRevoked()`. Same destructive variant, same 429 RateLimitError-first branch, same disabled-on-submit pattern.

---

### `frontend/src/tests/msw/account.handlers.ts` (NEW)

**Analog:** `frontend/src/tests/msw/keys.handlers.ts` (entire file, 32 lines) + `auth.handlers.ts:33` (logout 204 pattern)

**Full keys.handlers.ts to mirror:**
```typescript
import { http, HttpResponse } from 'msw';

export const keysHandlers = [
  http.get('/api/keys', () =>
    HttpResponse.json([
      {
        id: 1, name: 'default', prefix: 'whsk_abc1',
        created_at: '2026-04-29T12:00:00Z', last_used_at: null, status: 'active',
      },
    ]),
  ),
  http.post('/api/keys', async ({ request }) => { /* 201 + body */ }),
  http.delete('/api/keys/:id', () => new HttpResponse(null, { status: 204 })),
];
```

**Phase 15 module to write (RESEARCH §1071-1093):**
```typescript
import { http, HttpResponse } from 'msw';

export const accountHandlers = [
  http.get('/api/account/me', () =>
    HttpResponse.json({
      user_id: 1,
      email: 'alice@example.com',
      plan_tier: 'trial',
      trial_started_at: '2026-04-22T12:00:00Z',
      token_version: 0,
    }),
  ),
  http.delete('/api/account', () => new HttpResponse(null, { status: 204 })),
  http.post('/auth/logout-all', () => new HttpResponse(null, { status: 204 })),
  http.post('/billing/checkout', () =>
    HttpResponse.json(
      { detail: 'Not Implemented', status: 'stub', hint: 'Stripe integration arrives in v1.3' },
      { status: 501 },
    ),
  ),
];
```

---

### `frontend/src/tests/msw/handlers.ts` (MODIFY: barrel export)

**Analog (in same file):** lines 1-12

**Current barrel:**
```typescript
import { authHandlers } from './auth.handlers';
import { keysHandlers } from './keys.handlers';
import { wsHandlers } from './ws.handlers';
import { transcribeHandlers } from './transcribe.handlers';

export const handlers = [
  ...authHandlers,
  ...keysHandlers,
  ...wsHandlers,
  ...transcribeHandlers,
];
```

**Phase 15 change:** add `import { accountHandlers } from './account.handlers';` and `...accountHandlers` to the spread array.

---

### `frontend/src/tests/routes/AccountPage.test.tsx` (NEW)

**Analog:** `frontend/src/tests/routes/KeysDashboardPage.test.tsx` (entire file, 121 lines)

**Render-helper + auth-store seed pattern** (lines 22-36):
```typescript
function renderPage() {
  return render(
    <MemoryRouter>
      <KeysDashboardPage />
    </MemoryRouter>,
  );
}

describe('KeysDashboardPage', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: 1, email: 'alice@example.com', planTier: 'trial' },
    });
  });

  it('renders existing keys from /api/keys', async () => {
    renderPage();
    expect(await screen.findByText('default')).toBeInTheDocument();
    expect(screen.getByText(/whsk_abc1/)).toBeInTheDocument();
  });
```

**MSW handler-override pattern** (lines 43-46):
```typescript
it('shows empty state when no keys', async () => {
  server.use(http.get('/api/keys', () => HttpResponse.json([])));
  renderPage();
  expect(await screen.findByText(/no keys yet/i)).toBeInTheDocument();
});
```

**429 inline countdown pattern** (lines 102-119):
```typescript
it('429 on create-key surfaces retry-after countdown (no toast)', async () => {
  server.use(
    http.post('/api/keys', () =>
      HttpResponse.json(
        { detail: 'Too many' },
        { status: 429, headers: { 'Retry-After': '15' } },
      ),
    ),
  );
  /* user.click + assert findByText(/15s/) */
});
```

**Phase 15 tests (RESEARCH §1099-1117):** AccountPage renders email + plan-tier badge, error card on /me 500, reload-account retry, hides Upgrade button when planTier='pro'. Seed `useAuthStore.setState({ user: { id: 1, email: 'alice@example.com', planTier: 'trial', trialStartedAt: null, tokenVersion: 0 }, isHydrating: false })` in beforeEach.

---

### `frontend/src/tests/components/{Delete,LogoutAll,UpgradeInterest}Dialog.test.tsx` (NEW)

**Analog:** `KeysDashboardPage.test.tsx` (specifically lines 49-66 for create-flow pattern, lines 86-100 for revoke-flow pattern)

**Create-flow pattern** (lines 49-66):
```typescript
it('create-key flow: opens modal -> submits -> shows plaintext once', async () => {
  const user = userEvent.setup();
  renderPage();
  await screen.findByText('default');
  const buttons = screen.getAllByRole('button', { name: /create key/i });
  await user.click(buttons[0]);
  const nameInput = await screen.findByLabelText(/name/i);
  await user.type(nameInput, 'my-laptop');
  await user.click(screen.getByRole('button', { name: /^create$/i }));
  const plaintext = await screen.findByTestId('created-key-plaintext');
  expect(plaintext.textContent).toContain('whsk_xyz2_');
});
```

**Revoke-confirm pattern** (lines 86-100):
```typescript
it('revoke flow: clicks revoke -> confirms -> calls DELETE /api/keys/:id', async () => {
  let deleteCalledWith: string | null = null;
  server.use(
    http.delete('/api/keys/:id', ({ params }) => {
      deleteCalledWith = String(params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const user = userEvent.setup();
  renderPage();
  await screen.findByText('default');
  await user.click(screen.getByRole('button', { name: /revoke default/i }));
  await user.click(await screen.findByRole('button', { name: /^revoke$/i }));
  await waitFor(() => expect(deleteCalledWith).toBe('1'));
});
```

**Auto-close fake-timers pattern (RESEARCH §1110, UpgradeInterestDialog):** `vi.useFakeTimers()` → user clicks send → assert success → `vi.advanceTimersByTime(2000)` → assert dialog closed. Mirror existing fake-timer use elsewhere in repo if present (search `vi.useFakeTimers` if needed at plan time).

---

### `frontend/src/tests/lib/stores/authStore.test.ts` (EXTEND)

**Analog (same file):** lines 14-86

**Existing test pattern** (lines 22-30):
```typescript
it('login sets user from /auth/login response', async () => {
  await useAuthStore.getState().login('alice@example.com', 'password123');
  const u = useAuthStore.getState().user;
  expect(u).not.toBe(null);
  expect(u!.id).toBe(1);
  expect(u!.email).toBe('alice@example.com');
  expect(u!.planTier).toBe('trial');
});
```

**Phase 15 tests to add (RESEARCH §1112-1117):**
```typescript
it('refresh() populates user from /me', async () => {
  await useAuthStore.getState().refresh();
  expect(useAuthStore.getState().user!.email).toBe('alice@example.com');
  expect(useAuthStore.getState().isHydrating).toBe(false);
});

it('refresh() 401 leaves user null without redirect', async () => {
  server.use(
    http.get('/api/account/me', () =>
      HttpResponse.json({ detail: 'Authentication required' }, { status: 401 }),
    ),
  );
  await useAuthStore.getState().refresh();
  expect(useAuthStore.getState().user).toBe(null);
  expect(useAuthStore.getState().isHydrating).toBe(false);
});
```

`beforeEach` already resets `user: null` (line 16); extend to reset `isHydrating: true`.

---

### `frontend/src/tests/lib/apiClient.test.ts` (EXTEND)

**Analog (same file):** `apiClient.test.ts:69-80` (suppress401Redirect for POST already covered)

**Existing pattern to extend to GET + DELETE:**
```typescript
it('401 does NOT redirect when suppress401Redirect=true', async () => {
  const before = window.location.href;
  server.use(
    http.post('/api/test', () =>
      HttpResponse.json({ detail: 'Authentication required' }, { status: 401 }),
    ),
  );
  await expect(
    apiClient.post('/api/test', null, { suppress401Redirect: true }),
  ).rejects.toBeInstanceOf(AuthRequiredError);
  expect(window.location.href).toBe(before);
});
```

**Phase 15 tests to add:**
1. GET with `suppress401Redirect: true` → no redirect (clone of POST test)
2. DELETE with body sends JSON body — assert `request.json()` returns `{ email_confirm: 'x@y.com' }`

---

## Shared Patterns

### Cookie-clearing on logout/destructive routes

**Source:** `app/api/auth_routes.py:101-104` (private helper to extract) + `:182-194` (correct return-Response pattern)

**Apply to:** `auth_routes.py:/logout-all`, `account_routes.py:DELETE /api/account`

```python
# After extraction to app/api/_cookie_helpers.py:
def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")

# In every route that mutates auth cookies:
response = Response(status_code=status.HTTP_204_NO_CONTENT)
clear_auth_cookies(response)
return response
```

**Anti-pattern (T-15-04):** `Depends(Response)` + `return Response(...)` — Set-Cookie headers dropped. Verifier-grep should flag.

---

### Tiger-style boundary assertions in services

**Source:** `app/services/auth/auth_service.py:91-97` (logout_all_devices guard)

**Apply to:** `AccountService.delete_account`, `AccountService.get_account_summary`

```python
def method(self, user_id: int, ...) -> ...:
    assert user_id > 0, "user_id must be positive"
    assert email_confirm and email_confirm.strip(), "email_confirm required"
    user = self._user_repository.get_by_id(user_id)
    if user is None:
        raise InvalidCredentialsError()    # generic anti-enum
    # ... business logic
```

---

### Anti-enumeration generic errors

**Source:** `app/api/auth_routes.py:55-58 + 107-113` + `app/core/exceptions.py:612-621` (`InvalidCredentialsError`)

**Apply to:** `delete_account` 400-mismatch (use `ValidationError(message="Confirmation email does not match", code="EMAIL_CONFIRM_MISMATCH")`), `get_account_summary` user-missing (use `InvalidCredentialsError`).

```python
raise ValidationError(
    message="Confirmation email does not match",
    code="EMAIL_CONFIRM_MISMATCH",
    user_message="Confirmation email does not match",
)
```

Already wired to 422 via `validation_error_handler`; mismatch returns the JSON body shape:
```json
{ "error": { "message": "...", "code": "EMAIL_CONFIRM_MISMATCH", "correlation_id": "..." } }
```

NOTE: research locks 400 status code for the mismatch (CONTEXT §49 + RESEARCH §1144). If `validation_error_handler` defaults to 422, plan must either (a) handle 400 explicitly via `HTTPException(400, ...)` in the route OR (b) inspect the existing handler output for actual status mapping. Mirror the existing 422 register-failed flow (`test_auth_routes.py:135-142`) but with a 400 wrapper if needed.

---

### Apiclient subtype-first error branch

**Source:** `frontend/src/components/dashboard/CreateKeyDialog.tsx:71-79` + `frontend/src/routes/KeysDashboardPage.tsx:34-46` + `RevokeKeyDialog.tsx:45-54`

**Apply to:** every dialog catch block + AccountPage refresh catch block.

```typescript
} catch (err) {
  // RateLimitError extends ApiClientError — handle subtype FIRST
  if (err instanceof RateLimitError) {
    setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`);
  } else if (err instanceof ApiClientError) {
    setError('Could not <verb>.');
  } else {
    setError('Could not <verb>.');
  }
}
```

**For DeleteAccountDialog only:** branch ApiClientError on `statusCode === 400` for the email-mismatch copy (RESEARCH §1029-1033).

**For UpgradeInterestDialog only:** branch ApiClientError on `statusCode === 501` and treat as success state (T-15-07 — RESEARCH §808-815).

---

### Dialog show-once / confirm-then-action state machine

**Source:** `CreateKeyDialog.tsx:40-82` (form-state) + `RevokeKeyDialog.tsx:34-57` (confirm-action)

**Apply to:** all 3 new dialogs.

Common shape:
```typescript
const [submitting, setSubmitting] = useState(false);
const [error, setError] = useState<string | null>(null);
// optionally const [success, setSuccess] = useState(false);  for UpgradeInterest
```

Submit handler: `setSubmitting(true)` → `await api(...)` → on success either `onSuccess()` callback OR `setSuccess(true)` → catch with subtype-first pattern → finally `setSubmitting(false)`.

---

### MSW handler module + barrel export

**Source:** `frontend/src/tests/msw/{auth,keys,ws,transcribe}.handlers.ts` + `handlers.ts`

**Apply to:** `account.handlers.ts` (NEW) + barrel modification.

Single named export `export const <domain>Handlers = [...]`; barrel imports + spreads.

---

### Slim FastAPI test app fixture (per-test Container override)

**Source:** `tests/integration/test_account_routes.py:55-117` (5-fixture stack)

**Apply to:** any new integration test file (preferred extend existing files instead of new file per RESEARCH §1141).

```python
@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str: ...
@pytest.fixture
def session_factory(tmp_db_url): ...
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

This fixture stack already exists in `test_account_routes.py` — extend in place, do not duplicate.

---

## No Analog Found

(none) — every Phase 15 file has a strong analog in the existing codebase. The phase is almost entirely integration work; no novel architectural primitives required.

---

## Metadata

**Analog search scope:**
- `app/api/{auth_routes,account_routes,billing_routes,key_routes,dependencies}.py`
- `app/api/schemas/{auth,billing,key}_schemas.py`
- `app/services/{account_service,auth/auth_service}.py`
- `app/domain/{entities/user,repositories/user_repository}.py`
- `app/infrastructure/database/repositories/sqlalchemy_user_repository.py`
- `app/infrastructure/database/models.py` (FK ondelete audit)
- `app/core/{container,exceptions}.py`
- `frontend/src/lib/{apiClient,api/keysApi,stores/authStore}.ts`
- `frontend/src/routes/{KeysDashboardPage,AccountStubPage,RequireAuth,AppRouter}.tsx`
- `frontend/src/components/{ui/{card,dialog},dashboard/{CreateKeyDialog,RevokeKeyDialog}}.tsx`
- `frontend/src/tests/{setup,lib/{apiClient,stores/authStore},msw/{auth,keys,handlers},routes/KeysDashboardPage}.test.{ts,tsx}`
- `tests/integration/{test_account_routes,test_auth_routes,test_billing_routes}.py`

**Files scanned:** ~30 source + 10 test files; line-by-line read of analog regions for every Phase 15 target.

**Pattern extraction date:** 2026-04-29
