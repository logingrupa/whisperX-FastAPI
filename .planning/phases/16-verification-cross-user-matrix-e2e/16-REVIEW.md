---
phase: 16-verification-cross-user-matrix-e2e
reviewed: 2026-04-29T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - tests/integration/_phase16_helpers.py
  - tests/integration/test_security_matrix.py
  - tests/integration/test_jwt_attacks.py
  - tests/integration/test_csrf_enforcement.py
  - tests/integration/test_ws_ticket_safety.py
  - tests/integration/test_migration_smoke.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-04-29T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Six integration test files covering VERIFY-01 through VERIFY-08. Structure
is solid: single helper module, function-scoped fixtures with per-test SQLite
DBs (no cross-test contamination), flat conditionals, tiger-style failure
messages on HTTP assertions. Three warnings and three info items found. No
critical issues.

Key concerns:
- `_seed_admin_user_and_assign_tasks` uses `admin_id` before guarding against
  `None` — UPDATE runs with a potential `NULL` user_id.
- JWT attack tests assert 401 status only; the T-13-05 anti-leak body invariant
  (`"Authentication required"`) documented in the file's own docstring is never
  actually verified.
- `_close_code_from_disconnect` is copy-pasted verbatim in two files despite
  `_phase16_helpers.py` existing as the DRY single source.

---

## Warnings

### WR-01: `admin_id` None-guard placed after the UPDATE it is meant to protect

**File:** `tests/integration/test_migration_smoke.py:101-103`

**Issue:** `admin_id` is fetched via `SELECT id FROM users WHERE email = ?`
(line 98-100) and then immediately passed into
`UPDATE tasks SET user_id = ?` (line 101) before the
`assert admin_id is not None` guard fires on line 103.
If the INSERT silently failed or the SELECT returned no row (e.g. schema drift,
email uniqueness violated), the UPDATE would write `user_id = NULL` to all
task rows — causing the subsequent `upgrade head` to fail with a confusing
pre-flight error rather than a clear assertion failure.

**Fix:** Move the assertion before the UPDATE:

```python
admin_id = conn.exec_driver_sql(
    "SELECT id FROM users WHERE email = 'admin@phase16.example.com'"
).scalar()
assert admin_id is not None, "admin user insert returned no id"   # guard FIRST
conn.exec_driver_sql("UPDATE tasks SET user_id = ?", (admin_id,))
```

---

### WR-02: JWT attack tests only assert status code — T-13-05 body invariant unverified

**File:** `tests/integration/test_jwt_attacks.py:192`, `test_jwt_attacks.py:214`, `test_jwt_attacks.py:235`

**Issue:** The file docstring states:
> "every rejection collapses through `decode_session` and surfaces as the
> generic `'Authentication required'` 401 (T-13-05 anti-leak)"

But each test ends with only:
```python
assert response.status_code == 401, response.text
```

This does NOT verify the anti-leak invariant. A 401 from the wrong exception
handler (e.g. FastAPI's built-in `HTTPException` with `"Not authenticated"`,
or a misconfigured `InvalidCredentialsError` handler returning a leak-prone
body) would still pass the test. The specific `{"detail": "Authentication
required"}` body that proves single-decode-site collapse is never checked.

**Fix:** Add a body assertion to all three test bodies:

```python
assert response.status_code == 401, response.text
assert response.json()["detail"] == "Authentication required", (
    f"T-13-05 anti-leak body mismatch: {response.text}"
)
```

---

### WR-03: `_insert_task` UUID uses float timestamp — collision risk on fast/mocked clocks

**File:** `tests/integration/_phase16_helpers.py:136-138`

**Issue:**
```python
task_uuid = f"uuid-u{user_id}-{datetime.now(timezone.utc).timestamp()}"
```
`timestamp()` returns a float. Two calls within the same sub-millisecond
window (e.g. when `datetime` is monkeypatched to a frozen clock, as in
`test_expired_ticket_close_1008`) produce an identical UUID string. The `uuid`
column has a UNIQUE constraint — the second insert would raise `IntegrityError`
and fail the test with an opaque DB error rather than a useful assertion.

`test_expired_ticket_close_1008` issues the ticket before the monkeypatch, so
the frozen clock does not affect `_insert_task` in the current test. However
future tests that monkeypatch before inserting would silently collide.

**Fix:** Use `uuid.uuid4()` for guaranteed uniqueness:

```python
import uuid as _uuid

task_uuid = str(_uuid.uuid4())
```

---

## Info

### IN-01: `_close_code_from_disconnect` copy-pasted — should be in `_phase16_helpers`

**File:** `tests/integration/test_ws_ticket_safety.py:130-132`

**Issue:** Identical function defined in both `test_ws_ticket_safety.py:130`
and `test_ws_ticket_flow.py:165` (pre-existing file, outside Phase 16 scope):

```python
def _close_code_from_disconnect(exc: WebSocketDisconnect) -> int:
    """Extract the close code in a Starlette-version-tolerant way."""
    return int(exc.code)
```

`_phase16_helpers.py` already exports `WS_POLICY_VIOLATION`. The helper
belongs there alongside it. DRY violation across two test files.

**Fix:** Add to `_phase16_helpers.py`:
```python
from starlette.websockets import WebSocketDisconnect

def _close_code_from_disconnect(exc: WebSocketDisconnect) -> int:
    """Extract the close code in a Starlette-version-tolerant way."""
    return int(exc.code)
```
Import in `test_ws_ticket_safety.py` and `test_ws_ticket_flow.py` from helpers.

---

### IN-02: WS close-code assertions lack failure messages (tiger-style gap)

**File:** `tests/integration/test_ws_ticket_safety.py:170`, `205`, `247`

**Issue:** All three terminal assertions:
```python
assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION
```
have no failure message. When these fail, the output shows only
`AssertionError` with no indication of what close code was actually received.
Other assertions in the suite correctly append `response.text`.

**Fix:**
```python
actual = _close_code_from_disconnect(exc_info.value)
assert actual == WS_POLICY_VIOLATION, (
    f"expected close 1008, got {actual}"
)
```

---

### IN-03: `REPO_ROOT` imported but unused in `test_migration_smoke.py`

**File:** `tests/integration/test_migration_smoke.py:28-31`

**Issue:**
```python
from tests.integration._phase16_helpers import REPO_ROOT, _run_alembic

# REPO_ROOT re-exported via import for forward-compat with future helpers.
_ = REPO_ROOT
```
`REPO_ROOT` is only consumed by `_run_alembic` internally (the helper already
has access). The `_ = REPO_ROOT` assignment is dead code with a speculative
"forward-compat" comment. `_run_alembic` passes `cwd=REPO_ROOT` itself — no
caller needs the constant. This violates DRY by importing something only
`_run_alembic` should own, and creates noise for future maintainers.

**Fix:** Remove the `REPO_ROOT` import and the `_ = REPO_ROOT` line:
```python
from tests.integration._phase16_helpers import _run_alembic
```

---

_Reviewed: 2026-04-29T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
