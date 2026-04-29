---
phase: 15
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - frontend/src/lib/apiClient.ts
  - frontend/src/tests/lib/apiClient.test.ts
  - app/api/_cookie_helpers.py
  - app/api/auth_routes.py
  - tests/unit/api/test_cookie_helpers.py
  - app/api/schemas/account_schemas.py
  - frontend/src/lib/api/accountApi.ts
  - frontend/src/tests/msw/account.handlers.ts
  - frontend/src/tests/msw/handlers.ts
autonomous: true
requirements: [UI-07, AUTH-06, SCOPE-06, BILL-05, BILL-06]
must_haves:
  truths:
    - "apiClient.get accepts {suppress401Redirect, headers} options object"
    - "apiClient.delete accepts optional JSON body second arg"
    - "clear_auth_cookies importable from app.api._cookie_helpers; auth_routes.py /logout uses the shared helper"
    - "AccountSummaryResponse and DeleteAccountRequest Pydantic schemas exist and validate"
    - "accountApi.ts exports fetchAccountSummary, logoutAllDevices, deleteAccount, submitUpgradeInterest"
    - "MSW account.handlers.ts spread into handlers.ts barrel"
  artifacts:
    - path: "frontend/src/lib/apiClient.ts"
      provides: "Extended get + delete signatures"
      contains: "suppress401Redirect"
    - path: "app/api/_cookie_helpers.py"
      provides: "clear_auth_cookies shared helper"
      exports: ["clear_auth_cookies", "SESSION_COOKIE", "CSRF_COOKIE"]
    - path: "app/api/schemas/account_schemas.py"
      provides: "AccountSummaryResponse + DeleteAccountRequest"
      exports: ["AccountSummaryResponse", "DeleteAccountRequest"]
    - path: "frontend/src/lib/api/accountApi.ts"
      provides: "Typed HTTP wrappers for account endpoints"
      exports: ["fetchAccountSummary", "logoutAllDevices", "deleteAccount", "submitUpgradeInterest", "AccountSummaryResponse"]
    - path: "frontend/src/tests/msw/account.handlers.ts"
      provides: "MSW mock handlers for /me, DELETE /api/account, /auth/logout-all, /billing/checkout"
      exports: ["accountHandlers"]
  key_links:
    - from: "frontend/src/tests/msw/handlers.ts"
      to: "frontend/src/tests/msw/account.handlers.ts"
      via: "named import + spread"
      pattern: "import.*accountHandlers.*from.*account\\.handlers"
    - from: "app/api/auth_routes.py"
      to: "app/api/_cookie_helpers.py"
      via: "import clear_auth_cookies"
      pattern: "from app\\.api\\._cookie_helpers import"
---

<objective>
Wave 0 groundwork: extend apiClient (get suppress401Redirect, delete body), extract shared `clear_auth_cookies` helper to break the auth_routes private-function dependency, declare backend Pydantic schemas, declare frontend accountApi typed module, declare MSW handlers. Unblocks Waves 1-3.

Purpose: Single-source-of-truth for HTTP client extensions, cookie helpers, schemas, and test mocks. Every later plan imports from these files.
Output: Six extended/new files. No new business logic — wiring + types only.
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
@frontend/src/lib/apiClient.ts
@frontend/src/lib/api/keysApi.ts
@frontend/src/tests/msw/keys.handlers.ts
@frontend/src/tests/msw/handlers.ts
@app/api/auth_routes.py
@app/api/schemas/auth_schemas.py

<interfaces>
<!-- Pulled verbatim from codebase. Executor uses these directly — no exploration needed. -->

From frontend/src/lib/apiClient.ts (current state, lines 155-166):
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
`request()` already supports `body` on every method (buildBody) and `suppress401Redirect` on every method (line 131). Only the public exports object needs change. Existing class fields (e.g. ApiClientError, RateLimitError, AuthRequiredError) are preserved.

From app/api/auth_routes.py (lines 32-104, current state):
```python
SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"
# ...
def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
```
The new shared helper exposes `clear_auth_cookies` (no leading underscore — public). auth_routes.py logout (line 193) imports + uses it.

From app/api/schemas/auth_schemas.py (lines 1-44):
```python
from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field

class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="...")
    password: str = Field(..., min_length=8, max_length=128, description="...")
```

From frontend/src/lib/api/keysApi.ts (full file pattern):
```typescript
import { apiClient } from '@/lib/apiClient';
export interface ApiKeyListItem { id: number; name: string; prefix: string; created_at: string; last_used_at: string | null; status: 'active' | 'revoked'; }
export function fetchKeys(): Promise<ApiKeyListItem[]> { return apiClient.get<ApiKeyListItem[]>('/api/keys'); }
export function createKey(name: string): Promise<CreatedApiKey> { return apiClient.post<CreatedApiKey>('/api/keys', { name }); }
export function revokeKey(id: number): Promise<void> { return apiClient.delete<void>(`/api/keys/${id}`); }
```

From frontend/src/tests/msw/handlers.ts (current barrel, lines 1-12):
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
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend apiClient.get + apiClient.delete signatures with body / suppress401Redirect (DRY single fetch site invariant)</name>
  <files>frontend/src/lib/apiClient.ts, frontend/src/tests/lib/apiClient.test.ts</files>
  <read_first>
    - frontend/src/lib/apiClient.ts (full — verify request() already supports body + suppress on every method per RESEARCH §493-503)
    - frontend/src/tests/lib/apiClient.test.ts (existing POST suppress401Redirect test at lines 69-80 to mirror)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"frontend/src/lib/apiClient.ts (MODIFY: extend get + delete signatures)"
  </read_first>
  <behavior>
    - Test 1 (extends existing pattern at apiClient.test.ts:69-80): GET with `{suppress401Redirect: true}` does NOT redirect on 401; throws AuthRequiredError; window.location.href unchanged.
    - Test 2: GET with `{headers: {'X-Foo': 'bar'}}` forwards headers to request().
    - Test 3: DELETE with body `{email_confirm: 'x@y.com'}` sends a request body — assert MSW handler receives `await request.json()` returning `{ email_confirm: 'x@y.com' }`.
    - Test 4: DELETE without body argument (existing `revokeKey` callsite) still works — no-body request unaffected.
  </behavior>
  <action>
    Per D-01 (apiClient single fetch site invariant), modify ONLY the public exports object in `frontend/src/lib/apiClient.ts`. The internal `request()` function already supports `body` on every method and `suppress401Redirect` on every method — no changes there.

    Replace the `get` and `delete` lines verbatim:
    ```typescript
    get: <T>(path: string, opts?: { headers?: Record<string, string>; suppress401Redirect?: boolean }) =>
      request<T>({ method: 'GET', path, headers: opts?.headers, suppress401Redirect: opts?.suppress401Redirect }),
    // ... post / put / patch unchanged ...
    delete: <T>(path: string, body?: unknown) =>
      request<T>({ method: 'DELETE', path, body }),
    ```

    Caller migration check: `frontend/src/lib/api/keysApi.ts` calls `apiClient.get<ApiKeyListItem[]>('/api/keys')` (no headers) and `apiClient.delete<void>(\`/api/keys/${id}\`)` (no body) — both unaffected.

    No nested-if rule: keep this file flat. No `if (opts) { if (opts.headers) ... }` patterns. Optional chaining only.

    Tiger-style: no defensive Object.assign; use direct property access via optional chaining.

    Write the 4 tests above into `frontend/src/tests/lib/apiClient.test.ts` (extend file, do not duplicate `describe` block).
  </action>
  <verify>
    <automated>cd frontend && bun run vitest run src/tests/lib/apiClient.test.ts</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "get: <T>(path: string, opts?: { headers" frontend/src/lib/apiClient.ts` returns 1 line
    - `grep -n "delete: <T>(path: string, body?: unknown)" frontend/src/lib/apiClient.ts` returns 1 line
    - `grep -cE "^\s+if .*\bif\b" frontend/src/lib/apiClient.ts` returns 0 (nested-if invariant)
    - `cd frontend && bunx tsc --noEmit` exits 0 (TypeScript compiles)
    - vitest output shows 4 new test cases passing
    - Existing apiClient.test.ts tests still pass (no regression)
  </acceptance_criteria>
  <done>apiClient.get + delete carry expected new signatures; tsc green; all apiClient tests pass; nested-if grep returns 0.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Extract clear_auth_cookies to app/api/_cookie_helpers.py + migrate auth_routes.py /logout caller (DRY across auth + account routes)</name>
  <files>app/api/_cookie_helpers.py, app/api/auth_routes.py, tests/unit/api/test_cookie_helpers.py</files>
  <read_first>
    - app/api/auth_routes.py lines 1-50 (imports) + lines 32-53 (SESSION_COOKIE/CSRF_COOKIE constants) + lines 101-104 (`_clear_auth_cookies` helper) + lines 182-194 (logout returning new Response)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"app/api/_cookie_helpers.py (utility, NEW)"
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Pattern 1: Cookie-Clearing Route Returns Brand-New Response"
  </read_first>
  <behavior>
    - Test 1 (test_cookie_helpers.py): instantiating fastapi.Response, calling `clear_auth_cookies(response)`, raw_headers contain two `set-cookie` entries with `session=` + `Max-Age=0` and `csrf_token=` + `Max-Age=0`.
    - Test 2 (existing test_auth_routes.py::test_logout_clears_cookies): MUST still pass after auth_routes migration to the shared helper.
  </behavior>
  <action>
    Create `app/api/_cookie_helpers.py` containing exactly:
    ```python
    """Shared cookie helpers for auth-mutating routes.

    Single source of truth for session and CSRF cookie names plus the
    clear_auth_cookies function. Imported by auth_routes (logout, logout-all)
    and account_routes (delete account). DRY per CONTEXT D-01.
    """
    from __future__ import annotations

    from fastapi import Response

    SESSION_COOKIE = "session"
    CSRF_COOKIE = "csrf_token"


    def clear_auth_cookies(response: Response) -> None:
        """Delete both session and csrf cookies on the supplied Response.

        Caller MUST pass a freshly constructed Response (not a Depends-injected
        one) — FastAPI drops Set-Cookie headers from the injected response when
        the route returns an explicit Response. See auth_routes.logout for the
        canonical pattern (Phase 13-03 lesson).
        """
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
    ```

    Modify `app/api/auth_routes.py`:
    1. Add `from app.api._cookie_helpers import clear_auth_cookies` near other app.api imports
    2. Delete the local `SESSION_COOKIE`, `CSRF_COOKIE`, `_clear_auth_cookies` definitions (lines ~32-53 + 101-104)
    3. Replace any in-file uses of `SESSION_COOKIE`, `CSRF_COOKIE` with imports from `app.api._cookie_helpers` if needed by login/register/_set_auth_cookies. If `_set_auth_cookies` references the constants, import them too: `from app.api._cookie_helpers import SESSION_COOKIE, CSRF_COOKIE, clear_auth_cookies`.
    4. Replace `_clear_auth_cookies(response)` call at line ~193 with `clear_auth_cookies(response)`.

    Tiger-style: no leading underscore on the public helper (it crosses module boundaries now). No silent re-export.

    SRP: cookie clearing is an HTTP concern, not auth-domain — file lives at `app/api/_cookie_helpers.py` (leading underscore on filename indicates private-to-app.api, per Python convention used elsewhere in this codebase).

    Create `tests/unit/api/test_cookie_helpers.py`:
    ```python
    """Unit tests for app.api._cookie_helpers — DRY cookie clearing."""
    from __future__ import annotations

    import pytest
    from fastapi import Response

    from app.api._cookie_helpers import (
        CSRF_COOKIE,
        SESSION_COOKIE,
        clear_auth_cookies,
    )


    @pytest.mark.unit
    def test_clear_auth_cookies_emits_max_age_zero_for_both_cookies() -> None:
        response = Response()
        clear_auth_cookies(response)
        # Response.raw_headers is list[tuple[bytes, bytes]] of (name, value)
        cookie_headers = [
            value.decode("ascii").lower()
            for name, value in response.raw_headers
            if name == b"set-cookie"
        ]
        joined = "\n".join(cookie_headers)
        assert "session=" in joined
        assert "csrf_token=" in joined
        assert joined.count("max-age=0") == 2


    @pytest.mark.unit
    def test_cookie_constants_are_locked_strings() -> None:
        assert SESSION_COOKIE == "session"
        assert CSRF_COOKIE == "csrf_token"
    ```
  </action>
  <verify>
    <automated>pytest tests/unit/api/test_cookie_helpers.py tests/integration/test_auth_routes.py::test_logout_clears_cookies -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def clear_auth_cookies" app/api/_cookie_helpers.py` returns 1
    - `grep -c "def _clear_auth_cookies" app/api/auth_routes.py` returns 0 (old local helper deleted)
    - `grep -c "from app.api._cookie_helpers import" app/api/auth_routes.py` returns 1
    - `grep -cE "^\s+if .*\bif\b" app/api/_cookie_helpers.py` returns 0
    - `pytest tests/unit/api/test_cookie_helpers.py -q` shows 2 passing
    - `pytest tests/integration/test_auth_routes.py::test_logout_clears_cookies -q` still passes (no regression on /auth/logout)
    - `python -c "from app.api._cookie_helpers import clear_auth_cookies, SESSION_COOKIE, CSRF_COOKIE; print('OK')"` prints OK
  </acceptance_criteria>
  <done>Shared helper exists; auth_routes uses it; both unit + integration cookie tests green; no duplicate constant definitions.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Pydantic schemas (account_schemas.py) + accountApi.ts + MSW handlers + barrel update</name>
  <files>app/api/schemas/account_schemas.py, frontend/src/lib/api/accountApi.ts, frontend/src/tests/msw/account.handlers.ts, frontend/src/tests/msw/handlers.ts</files>
  <read_first>
    - app/api/schemas/auth_schemas.py (full — Pydantic v2 BaseModel + EmailStr + Field pattern)
    - frontend/src/lib/api/keysApi.ts (full — pattern for accountApi.ts)
    - frontend/src/tests/msw/keys.handlers.ts (full — MSW handler pattern)
    - frontend/src/tests/msw/handlers.ts (current barrel, lines 1-12)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"AccountSummaryResponse Schema [LOCKED]" + §"Frontend authStore.refresh Wiring" + §"Test Patterns/MSW handlers"
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"app/api/schemas/account_schemas.py" + §"frontend/src/lib/api/accountApi.ts" + §"frontend/src/tests/msw/account.handlers.ts"
  </read_first>
  <behavior>
    - Pydantic: AccountSummaryResponse parses `{user_id: 1, email: 'a@b.c', plan_tier: 'trial', trial_started_at: '2026-04-22T12:00:00+00:00', token_version: 0}` successfully and rejects malformed email with ValidationError.
    - Pydantic: DeleteAccountRequest parses `{email_confirm: 'a@b.c'}` and rejects malformed email at parse time (422 in HTTP context).
    - TypeScript: `import { fetchAccountSummary, logoutAllDevices, deleteAccount, submitUpgradeInterest } from '@/lib/api/accountApi'` resolves; tsc green.
    - MSW: handlers.ts barrel spreads accountHandlers; consuming `setupServer(...handlers)` in setup.ts intercepts /api/account/me, DELETE /api/account, /auth/logout-all, /billing/checkout (501).
  </behavior>
  <action>
    Per D-01 (DRY single accountApi.ts site) + D-04 (Pydantic v2 schemas under app/api/schemas/).

    **3a. Create `app/api/schemas/account_schemas.py`** verbatim from RESEARCH §551-572:
    ```python
    """Pydantic schemas for /api/account routes — Phase 15."""
    from __future__ import annotations

    from datetime import datetime

    from pydantic import BaseModel, EmailStr, Field


    class AccountSummaryResponse(BaseModel):
        """GET /api/account/me — server-side hydration source of truth."""

        user_id: int
        email: EmailStr
        plan_tier: str = Field(..., description="One of free|trial|pro|team")
        trial_started_at: datetime | None = None
        token_version: int = Field(..., description="For cross-tab refresh debounce")


    class DeleteAccountRequest(BaseModel):
        """DELETE /api/account body. email_confirm validated against user.email at boundary."""

        email_confirm: EmailStr = Field(
            ..., description="Must equal request.state.user.email (case-insensitive)"
        )
    ```

    **3b. Create `frontend/src/lib/api/accountApi.ts`** verbatim from RESEARCH §577-607:
    ```typescript
    /**
     * Phase 15 — typed HTTP wrappers for /api/account/* and /auth/logout-all.
     * Single fetch site for account-related endpoints (UI-11 invariant).
     */
    import { apiClient } from '@/lib/apiClient';

    export interface AccountSummaryResponse {
      user_id: number;
      email: string;
      plan_tier: 'free' | 'trial' | 'pro' | 'team';
      trial_started_at: string | null;
      token_version: number;
    }

    /**
     * Probe-style boot fetch — uses suppress401Redirect so a 401 throws
     * AuthRequiredError without forcing redirect (RequireAuth handles that).
     */
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

    /**
     * UpgradeInterestDialog hits /billing/checkout (501 stub in v1.2).
     * Caller treats ApiClientError with statusCode === 501 as success.
     */
    export function submitUpgradeInterest(message: string): Promise<void> {
      return apiClient.post<void>('/billing/checkout', { plan: 'pro', message });
    }
    ```

    **3c. Create `frontend/src/tests/msw/account.handlers.ts`** verbatim from RESEARCH §1071-1093:
    ```typescript
    /** MSW handlers for Phase 15 account/billing endpoints. */
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

    **3d. Modify `frontend/src/tests/msw/handlers.ts`** — add the import + spread:
    ```typescript
    import { authHandlers } from './auth.handlers';
    import { keysHandlers } from './keys.handlers';
    import { wsHandlers } from './ws.handlers';
    import { transcribeHandlers } from './transcribe.handlers';
    import { accountHandlers } from './account.handlers';

    export const handlers = [
      ...authHandlers,
      ...keysHandlers,
      ...wsHandlers,
      ...transcribeHandlers,
      ...accountHandlers,
    ];
    ```

    Self-explanatory naming locked: `fetchAccountSummary` not `getMe`; `submitUpgradeInterest` not `upgrade`; `accountHandlers` not `acct`.

    No tests created in this task — Wave 1+ tasks consume these mocks. Existing handlers.ts tests that import from this barrel must still pass (smoke).
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; bunx tsc --noEmit &amp;&amp; bun run vitest run src/tests/msw &amp;&amp; cd .. &amp;&amp; python -c "from app.api.schemas.account_schemas import AccountSummaryResponse, DeleteAccountRequest; AccountSummaryResponse(user_id=1, email='a@b.c', plan_tier='trial', token_version=0); DeleteAccountRequest(email_confirm='a@b.c'); print('schemas OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `python -c "from app.api.schemas.account_schemas import AccountSummaryResponse, DeleteAccountRequest"` exits 0
    - `grep -c "class AccountSummaryResponse" app/api/schemas/account_schemas.py` returns 1
    - `grep -c "class DeleteAccountRequest" app/api/schemas/account_schemas.py` returns 1
    - `grep -c "EmailStr" app/api/schemas/account_schemas.py` returns 2 (one per schema)
    - `grep -cE "^\s+if .*\bif\b" app/api/schemas/account_schemas.py` returns 0
    - `grep -c "export function fetchAccountSummary" frontend/src/lib/api/accountApi.ts` returns 1
    - `grep -c "export function logoutAllDevices" frontend/src/lib/api/accountApi.ts` returns 1
    - `grep -c "export function deleteAccount" frontend/src/lib/api/accountApi.ts` returns 1
    - `grep -c "export function submitUpgradeInterest" frontend/src/lib/api/accountApi.ts` returns 1
    - `grep -c "suppress401Redirect: true" frontend/src/lib/api/accountApi.ts` returns 1 (only on fetchAccountSummary)
    - `grep -c "accountHandlers" frontend/src/tests/msw/handlers.ts` returns 2 (import + spread)
    - `grep -cE "^\s+if .*\bif\b" frontend/src/lib/api/accountApi.ts` returns 0
    - `cd frontend && bunx tsc --noEmit` exits 0
    - BILL-06 stub presence verified (no new code — RESEARCH §69 + §1151 confirm Phase 13-05 already shipped):
      * `grep -q "/webhook" app/api/billing_routes.py` exits 0
      * `grep -q "Stripe-Signature" app/api/billing_routes.py` exits 0
      * `grep -q "501" app/api/billing_routes.py` exits 0
  </acceptance_criteria>
  <done>Schemas instantiate; accountApi.ts compiles; MSW handlers spread into barrel; all required exports verifiable via grep; BILL-06 webhook stub still present (no new code).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → FastAPI | Untrusted JSON body, untrusted cookies/CSRF tokens cross here |
| Test process → MSW intercept | In-process mock — no external network, but MSW must not leak into production bundle |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-15-04 | Information Disclosure | clear_auth_cookies caller pattern | mitigate | Helper docstring + auth_routes.logout pattern document mandatory `Response(204)` + `clear_auth_cookies(new_response)`; later plans (02, 04) verifier-grep for `Depends(Response)` + `return Response(...)` anti-pattern |
| T-15-08 | Tampering / DoS | apiClient.delete missing body | mitigate | W0 task extends signature; tsc catches missing arg; later integration tests exercise real body |
| T-15-11 | Information Disclosure | Schema serialization leaking secrets | mitigate | AccountSummaryResponse exposes only id/email/plan_tier/trial_started_at/token_version — no password_hash / token / csrf — Pydantic field allowlist enforces |
| T-15-05 | Information Disclosure | DeleteAccountRequest enumeration via parse vs match errors | accept | Parse-time 422 (malformed email) is observably different from service-layer 400 (mismatch). Acceptable: both require valid auth cookie first; no anonymous parse-vs-match leak path |
</threat_model>

<verification>
- All 3 tasks pass automated commands (vitest + pytest + tsc + python imports)
- No new nested-if patterns (`grep -cE "^\s+if .*\bif\b"` returns 0 across new files)
- Existing tests do NOT regress: `pytest tests/integration/test_auth_routes.py -q` and `cd frontend && bun run vitest run src/tests/lib/apiClient.test.ts` both green
- TypeScript compiles end-to-end: `cd frontend && bunx tsc --noEmit` exits 0
</verification>

<success_criteria>
1. `apiClient.get(path, {suppress401Redirect: true})` returns the parsed body without redirecting on 401
2. `apiClient.delete(path, body)` sends body as JSON; existing zero-arg callers still work
3. `from app.api._cookie_helpers import clear_auth_cookies` works app-wide; auth_routes.py /logout uses it
4. `AccountSummaryResponse` and `DeleteAccountRequest` parse correct payloads and reject malformed
5. `accountApi.ts` exports four functions backed by apiClient; tsc green
6. `handlers.ts` barrel includes `accountHandlers` so MSW intercepts /me, DELETE /api/account, /auth/logout-all, /billing/checkout
</success_criteria>

<output>
After completion, create `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-01-SUMMARY.md`
</output>
