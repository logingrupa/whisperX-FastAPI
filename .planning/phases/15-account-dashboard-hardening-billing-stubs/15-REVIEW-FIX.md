---
phase: 15-account-dashboard-hardening-billing-stubs
fixed_at: 2026-04-29T00:00:00Z
review_path: .planning/phases/15-account-dashboard-hardening-billing-stubs/15-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-04-29
**Source review:** .planning/phases/15-account-dashboard-hardening-billing-stubs/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (1 critical + 4 warning; info findings deferred per fix_scope=critical_warning)
- Fixed: 5
- Skipped: 0

**Verification:**
- `pytest tests/integration/test_auth_routes.py tests/integration/test_account_routes.py tests/unit/api/test_cookie_helpers.py` -> 34 passed
- `cd frontend && bun run vitest run` -> 84 passed across 15 test files
- Nested-if verifier-grep across all modified backend + frontend source files -> 0 matches

## Fixed Issues

### CR-01: `clear_auth_cookies` missing `domain` + `secure` — cookies not deleted in production

**Files modified:** `app/api/_cookie_helpers.py`
**Commit:** 0ca956b
**Applied fix:** Imported `get_settings` and now pass `domain` (from `settings.auth.COOKIE_DOMAIN or None`), `secure` (from `settings.auth.COOKIE_SECURE`), `httponly`, and `samesite='lax'` explicitly to `response.delete_cookie` for both SESSION_COOKIE and CSRF_COOKIE — mirrors the attributes set by `auth_routes._set_auth_cookies` so RFC 6265 §5.3 step-11 attribute matching succeeds and the browser actually drops both cookies. Updated module + function docstrings to document the contract.

### WR-01: Partial cascade commit window in `delete_account`

**Files modified:** `app/services/account_service.py`
**Commit:** 477972d
**Applied fix:** Renamed `_delete_tasks_for_user` -> `_delete_tasks_for_user_no_commit` (no longer commits internally). `delete_user_data` (SCOPE-05) now collects file names, stages tasks DELETE, commits once, then unlinks files — public contract unchanged. `delete_account` (SCOPE-06) now collects file names up-front, stages all three cascade DELETEs (tasks + rate_limit_buckets + user row) inside one transaction, and issues a single `session.commit()` at the end. On the race-defensive `InvalidCredentialsError` branch, calls `session.rollback()` first to undo the staged DELETEs from steps 1+2. File unlink is best-effort AFTER commit. Eliminates the partial-delete window where a step-2/3 failure would leave tasks gone but the user row alive.

### WR-02: `authStore.logout()` POSTs `/auth/logout` after server-side cookie clear

**Files modified:** `frontend/src/lib/stores/authStore.ts`, `frontend/src/components/dashboard/DeleteAccountDialog.tsx`, `frontend/src/components/dashboard/LogoutAllDialog.tsx`, `frontend/src/tests/components/DeleteAccountDialog.test.tsx`, `frontend/src/tests/components/LogoutAllDialog.test.tsx`
**Commit:** 8fb3e5e
**Applied fix:** Added `logoutLocal: () => void` to `AuthState` interface and store implementation — clears user state + broadcasts `{type:'logout'}` on the auth channel, no HTTP call. Wired both dialogs to call `logoutLocal()` (instead of `await logout()`) after their respective server calls (`deleteAccount` / `logoutAllDevices`) succeed; the server has already cleared cookies / invalidated JWTs, so the previous `await logout()` POST hit `/auth/logout` with a now-invalid cookie, 401'd, and raced `apiClient.redirectTo401()` against the dialog's own `navigate('/login')`, silently dropping the cross-tab broadcast. `logout()` (with HTTP round-trip) preserved unchanged for sidebar/header logout buttons. Updated both RTL test suites to seed and spy on `logoutLocal` instead of `logout`. Status: **fixed** (semantic correctness verified by RTL tests asserting `logoutLocal` was called and `/login` route rendered; cross-tab broadcast covered by existing authStore unit tests).

### WR-03: `get_account_summary` raises `InvalidCredentialsError` on missing user — surfaces as 401

**Files modified:** `app/api/account_routes.py`
**Commit:** 0f7cd4b
**Applied fix:** Expanded the `get_account_me` route docstring to document the deliberate 401-on-missing-row design: the global exception handler maps `InvalidCredentialsError` to 401, the frontend's `suppress401Redirect` flag on `fetchAccountSummary` makes apiClient throw `AuthRequiredError`, and `authStore.refresh()` silently clears the user — anti-enumeration parity with every other 401 surface (T-15-05). Future-maintainer warning included so the next reviewer does not "fix" this to 404 and re-introduce the enumeration leak.

### WR-04: Path traversal gap in `_delete_files`

**Files modified:** `app/services/account_service.py`
**Commit:** 8e8481d
**Applied fix:** Introduced `_unlink_within(base_dir, name)` helper which `Path.resolve()`s both the candidate (`base_dir / name`) and the base, then verifies containment via `is_relative_to`. Out-of-tree candidates are logged at `warning` level and skipped; in-tree candidates fall through to the existing `_unlink_safe` for OSError-tolerant unlink. `_delete_files` now iterates UPLOAD_DIR + TUS_UPLOAD_DIR through the new guard. SRP preserved: containment check is one method, OSError-tolerant unlink is another. Defence-in-depth against compromised migrations or direct DB writes injecting `../../etc/passwd`-style traversal strings.

---

_Fixed: 2026-04-29_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
