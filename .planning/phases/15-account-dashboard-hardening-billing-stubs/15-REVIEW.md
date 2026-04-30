---
phase: 15-account-dashboard-hardening-billing-stubs
reviewed: 2026-04-29T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - app/api/_cookie_helpers.py
  - app/api/account_routes.py
  - app/api/auth_routes.py
  - app/api/schemas/account_schemas.py
  - app/services/account_service.py
  - frontend/src/components/dashboard/DeleteAccountDialog.tsx
  - frontend/src/components/dashboard/LogoutAllDialog.tsx
  - frontend/src/components/dashboard/UpgradeInterestDialog.tsx
  - frontend/src/lib/api/accountApi.ts
  - frontend/src/lib/apiClient.ts
  - frontend/src/lib/stores/authStore.ts
  - frontend/src/main.tsx
  - frontend/src/routes/AccountPage.tsx
  - frontend/src/routes/AppRouter.tsx
  - frontend/src/routes/RequireAuth.tsx
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-04-29
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Phase 15 delivers POST /auth/logout-all (AUTH-06), GET /api/account/me (UI-07),
DELETE /api/account (SCOPE-06), the AccountPage three-card UI, three confirmation
dialogs, and authStore.refresh() / isHydrating boot probe.

DRY/SRP/tiger-style invariants are largely honored. Cookie helpers are
centralized, schemas are DTO-only, CSRF enforcement is wired correctly through
CsrfMiddleware → DualAuthMiddleware ordering. Error catch-chain ordering
(RateLimitError before ApiClientError) is consistent across all three dialogs and
AccountPage.

One critical security defect: `clear_auth_cookies` omits `domain` and `secure`
attributes on the deletion Set-Cookie, meaning browsers will silently ignore the
deletion when `COOKIE_DOMAIN` is configured in production. Four warnings cover
a partially-visible delete cascade window, a stale /auth/logout POST after account
deletion, a missing `get_account_summary` boundary assertion, and a path-traversal
gap in file deletion. Three info items address dead code, an eslint suppression,
and an unstable `useEffect` dependency.

---

## Critical Issues

### CR-01: `clear_auth_cookies` missing `domain` + `secure` — cookies not deleted in production

**File:** `app/api/_cookie_helpers.py:31-32`

**Issue:** `response.delete_cookie(SESSION_COOKIE, path="/")` omits the `domain`
and `secure` attributes. Per RFC 6265, a `Set-Cookie: Max-Age=0` header only
deletes a cookie when its `domain`, `path`, `secure`, and `httponly` attributes
exactly match the attributes used to set it. `_set_auth_cookies` in
`auth_routes.py` sets both cookies with `domain=settings.auth.COOKIE_DOMAIN` and
`secure=settings.auth.COOKIE_SECURE`. In any production deployment with
`COOKIE_DOMAIN` configured (e.g., `.example.com`), the deletion headers emitted
by `clear_auth_cookies` will not match and the browser will silently keep the
session and CSRF cookies alive. POST /auth/logout, POST /auth/logout-all, and
DELETE /api/account all hit this path — none of them actually clear cookies in
production.

**Fix:**
```python
# app/api/_cookie_helpers.py

from app.core.config import get_settings

def clear_auth_cookies(response: Response) -> None:
    """Delete both session and csrf cookies on the supplied Response.

    Attributes MUST match those used in _set_auth_cookies exactly, or the
    browser will ignore the deletion (RFC 6265 §5.3 step 11).
    """
    settings = get_settings()
    domain = settings.auth.COOKIE_DOMAIN or None
    secure = settings.auth.COOKIE_SECURE

    response.delete_cookie(SESSION_COOKIE, path="/", domain=domain, secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", domain=domain, secure=secure, httponly=False, samesite="lax")
```

---

## Warnings

### WR-01: Partial cascade commit window in `delete_account` — tasks deleted, user row survives on Step 2/3 failure

**File:** `app/services/account_service.py:161-181`

**Issue:** `delete_account` calls `delete_user_data(user_id)` at Step 1, which
internally calls `_delete_tasks_for_user` which does `self.session.commit()` at
line 207. If Step 2 (rate_limit_buckets DELETE) or Step 3 (`user_repository.delete`)
raises an exception, the transaction is already committed — tasks are gone but the
user row survives. Re-attempts via the race-defensive `InvalidCredentialsError`
path (line 180) would then fail to re-delete tasks (already gone) while the user
row stays alive, leaving the account in a broken half-deleted state. The comment
at line 159 says "steps are independent and idempotent" — that is true for
re-runs, but a partial failure on first run creates permanent data incoherence
(user can log back in with no tasks but an account that "exists").

**Fix:** Defer the intermediate commit — collect file names, issue all three
DELETEs in one transaction, commit once at the end. Since the final
`session.commit()` already covers the user deletion, remove the intermediate
commit from `_delete_tasks_for_user` when called from `delete_account`:

```python
def delete_account(self, user_id: int, email_confirm: str) -> dict[str, int]:
    # ... assertions + guards ...

    # Collect before any deletions (tasks row gone after delete)
    file_names = self._collect_user_file_names(user_id)

    # Step 1: tasks only — no intermediate commit
    tasks_deleted = self._delete_tasks_for_user_no_commit(user_id)

    # Step 2: rate_limit_buckets
    bucket_count = self.session.execute(...).rowcount or 0

    # Step 3: user row (ORM cascade)
    deleted = self._user_repository.delete(user_id)
    if not deleted:
        raise InvalidCredentialsError()

    # Single atomic commit for all three steps
    self.session.commit()

    # File deletion is best-effort, after DB commit
    files_deleted = self._delete_files(file_names)
    ...
```

### WR-02: `authStore.logout()` POSTs `/auth/logout` after `DELETE /api/account` — session already invalid

**File:** `frontend/src/components/dashboard/DeleteAccountDialog.tsx:80`

**Issue:** After `deleteAccount()` succeeds at line 79, the account is gone and
the session cookie is cleared server-side. `await logout()` at line 80 then calls
`apiClient.post('/auth/logout')` (authStore.ts:120), but the session cookie no
longer authenticates — `/auth/logout` is not on `PUBLIC_ALLOWLIST` in
`dual_auth.py`, so DualAuthMiddleware returns a 401. `apiClient` calls
`redirectTo401()` (setting `window.location.href = '/login?next=...'`) before the
`navigate('/login', { replace: true })` at line 81 can execute. `broadcast('logout')`
(authStore.ts:122) is also never reached, so cross-tab sync is skipped.

In practice the user still lands on /login, but: (a) the `next=` param is
injected unnecessarily, (b) cross-tab logout broadcast is silently dropped,
(c) the `set({ user: null })` update at authStore.ts:121 is skipped.

**Fix:** After a successful `deleteAccount()`, clear local state directly instead
of calling `logout()`:

```typescript
// DeleteAccountDialog.tsx onSubmit
await deleteAccount(confirmEmail);
// Account deleted: session gone, no point POSTing /auth/logout.
// Clear state + broadcast directly.
useAuthStore.getState().clearUser();  // add clearUser() action to authStore
navigate('/login', { replace: true });
```

Or add a `logoutLocal()` action to authStore that only does `set({ user: null })` +
`broadcast({ type: 'logout' })` without the HTTP call, and use it here and in
LogoutAllDialog (same pattern applies there at LogoutAllDialog.tsx:44).

### WR-03: `get_account_summary` raises `InvalidCredentialsError` on missing user — surfaces as 401 to authenticated caller

**File:** `app/services/account_service.py:88-90`

**Issue:** `get_account_summary` raises `InvalidCredentialsError` when
`get_by_id` returns None (line 90). The global exception handler maps
`InvalidCredentialsError` to HTTP 401. An authenticated caller who hits GET
`/api/account/me` receives a 401, which apiClient interprets as expired session
and redirects to `/login?next=/dashboard/account`. The user's session is valid —
only their user row is gone (race-condition delete as documented). Returning 401
is semantically misleading and will cause the browser to immediately redirect and
flash `/login` rather than showing "account not found."

The comment acknowledges this as anti-enumeration for the race case — reasonable
intent — but the Pydantic schema cannot be populated from a 401 body, and the
frontend's `suppress401Redirect: true` flag on `fetchAccountSummary` means
`AuthRequiredError` is thrown (not redirected), so authStore.refresh() silently
clears the user. In effect the race-delete scenario logs the user out silently
rather than showing an error message — acceptable UX, but the semantics are
misleading to future maintainers.

**Fix:** Document the deliberate 401-on-missing-row decision explicitly in the
route docstring and add a `# noqa: auth-overloaded-for-anti-enum` marker, so
the next reviewer understands this is intentional and not a missing 404 handler:

```python
@account_router.get("/me", response_model=AccountSummaryResponse)
async def get_account_me(...) -> AccountSummaryResponse:
    """GET /api/account/me — return account summary for client hydration (UI-07).

    InvalidCredentialsError from service (user row gone — race-condition delete)
    surfaces as 401 via the global handler. Intentional anti-enumeration:
    authenticated-but-missing == session-expired from the client's perspective.
    authStore.refresh() catches AuthRequiredError and clears user silently.
    """
```

Severity: warning (logic is defensible but fragile across future maintenance).

### WR-04: Path traversal gap in `_delete_files` — no boundary check on `file_name` from DB

**File:** `app/services/account_service.py:213-214`

**Issue:** `_collect_user_file_names` returns raw `file_name` values from the
`tasks` table and `_delete_files` joins them directly onto `UPLOAD_DIR` with
`UPLOAD_DIR / name`. `pathlib.Path.__truediv__` does NOT canonicalize: if `name`
contains `../../../etc/passwd`, the resolved path escapes `UPLOAD_DIR`. Although
`file_name` is stored by the application at upload time and is presumably
controlled, there is no defense-in-depth guard. A compromised migration or
direct DB write could insert a traversal sequence that would cause user
self-delete to unlink arbitrary files.

**Fix:** Add a containment assertion in `_unlink_safe` or `_delete_files`:

```python
def _delete_files(self, file_names: list[str]) -> int:
    count = 0
    for name in file_names:
        for base_dir in (UPLOAD_DIR, TUS_UPLOAD_DIR):
            candidate = (base_dir / name).resolve()
            if not candidate.is_relative_to(base_dir.resolve()):
                logger.warning("Skipping out-of-tree path name=%s", name)
                continue
            count += self._unlink_safe(candidate)
    return count
```

---

## Info

### IN-01: Dead code — redundant `else` branch in `LogoutAllDialog` catch block

**File:** `frontend/src/components/dashboard/LogoutAllDialog.tsx:51-54`

**Issue:** Both the `ApiClientError` branch (line 51) and the final `else`
(line 52) set the same string `'Could not sign out. Try again.'`. The `else`
branch is unreachable dead code; any non-ApiClientError (non-RateLimitError,
non-ApiClientError) would be caught there, but ApiClientError is the base class
of all thrown errors from apiClient, so unknown Error instances would only reach
`else` for programming errors — in which case swallowing them silently is wrong
anyway.

**Fix:**
```typescript
} catch (err) {
  if (err instanceof RateLimitError) {
    setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
  } else {
    // ApiClientError and unexpected errors both show the same copy.
    setError('Could not sign out. Try again.');
  }
}
```

### IN-02: `eslint-disable-next-line react-hooks/exhaustive-deps` suppresses a real warning in `UpgradeInterestDialog`

**File:** `frontend/src/components/dashboard/UpgradeInterestDialog.tsx:71`

**Issue:** The `useEffect` at line 65 depends on `handleClose` which is
recreated on every render (not wrapped in `useCallback`). The eslint suppression
hides this. If `success` flips to `true` while the component is simultaneously
re-rendering (e.g., parent prop change), the `handleClose` captured at effect
registration time may be stale. In practice the risk is low because `success` is
only set `true` once and the auto-close fires 2s later, but the suppression
papers over the issue rather than fixing it.

**Fix:**
```typescript
// Wrap handleClose in useCallback so the effect dependency is stable:
const handleClose = useCallback(() => {
  reset();
  onOpenChange(false);
}, [onOpenChange]);

useEffect(() => {
  if (!success) return;
  const timer = setTimeout(handleClose, SUCCESS_AUTO_CLOSE_MS);
  return () => clearTimeout(timer);
}, [success, handleClose]);
// Remove eslint-disable comment
```

### IN-03: `AccountPage.refresh` defined inline — missing `useCallback`, triggers ESLint exhaustive-deps warning

**File:** `frontend/src/routes/AccountPage.tsx:89-107`

**Issue:** `refresh` is defined as a plain `async` arrow function at line 89,
then called from `useEffect(() => { refresh(); }, [])` at line 109. ESLint
react-hooks/exhaustive-deps would flag `refresh` as a missing dependency.
The empty `[]` array is intentional (mount-once), but the missing `useCallback`
means a future developer adding `refresh` to the dependency array would introduce
an infinite re-render loop.

**Fix:**
```typescript
const refresh = useCallback(async () => {
  setError(null);
  setSummary(null);
  try {
    const data = await fetchAccountSummary();
    setSummary(data);
  } catch (err) {
    if (err instanceof RateLimitError) {
      setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
      return;
    }
    setError('Could not load account.');
  }
}, []); // fetchAccountSummary is a module-level stable reference

// import useCallback at line 1
```

---

_Reviewed: 2026-04-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
