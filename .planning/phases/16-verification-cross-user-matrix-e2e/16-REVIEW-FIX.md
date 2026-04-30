---
phase: 16-verification-cross-user-matrix-e2e
fixed_at: 2026-04-29T00:00:00Z
review_path: .planning/phases/16-verification-cross-user-matrix-e2e/16-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 16: Code Review Fix Report

**Fixed at:** 2026-04-29T00:00:00Z
**Source review:** .planning/phases/16-verification-cross-user-matrix-e2e/16-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (3 warnings, 0 critical; info findings out of scope)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `admin_id` None-guard placed after the UPDATE it is meant to protect

**Files modified:** `tests/integration/test_migration_smoke.py`
**Commit:** f4cc9f1
**Applied fix:** Moved `assert admin_id is not None, "admin user insert returned no id"` to fire BEFORE the `UPDATE tasks SET user_id = ?` statement so a missing admin row trips a clear assertion failure rather than writing `user_id = NULL` and surfacing as an opaque pre-flight error in `upgrade head`. Removed the duplicate post-dispose assertion (was redundant after move).

### WR-02: JWT attack tests only assert status code — T-13-05 body invariant unverified

**Files modified:** `tests/integration/test_jwt_attacks.py`
**Commit:** 4e2397f
**Applied fix:** Added `assert response.json()["detail"] == "Authentication required"` body check after each `status_code == 401` assertion in `test_alg_none_jwt_returns_401`, `test_tampered_jwt_returns_401`, and `test_expired_jwt_returns_401`. Each test runs across 2 transports (bearer/cookie) via `@pytest.mark.parametrize("transport", _TRANSPORTS)` so the single textual change to each test body covers all 6 cases. Failure message includes `response.text` for debug visibility.

### WR-03: `_insert_task` UUID uses float timestamp — collision risk on fast/mocked clocks

**Files modified:** `tests/integration/_phase16_helpers.py`
**Commit:** 3f6fb27
**Applied fix:** Replaced `task_uuid = f"uuid-u{user_id}-{datetime.now(timezone.utc).timestamp()}"` with `task_uuid = str(uuid.uuid4())`. Added `import uuid` to the standard-library import block; removed the now-unused `from datetime import datetime, timezone` import (verified zero remaining `datetime`/`timezone` references via grep). Eliminates collision risk under monkeypatched/frozen clocks while preserving the column's UNIQUE constraint guarantees.

## Verification

**AST syntax check:** All three modified files parse cleanly via `ast.parse`.

**Regression suite:** `pytest tests/integration/test_migration_smoke.py tests/integration/test_jwt_attacks.py tests/integration/test_security_matrix.py tests/integration/test_csrf_enforcement.py tests/integration/test_ws_ticket_safety.py -q`
- Collected: 34 tests
- Result: **34 passed** in 45.79s
- Warnings: 57 (all pre-existing — `MatplotlibDeprecationWarning` from pyannote, `InsecureKeyLengthWarning` from pyjwt for tests using short test secrets — none introduced by these fixes)

**Code-quality invariants preserved:**
- DRY — single shared helper module retained; no duplication introduced.
- SRP — each helper still does one job; assertion-before-UPDATE keeps `_seed_admin_user_and_assign_tasks` single-purpose.
- Tiger-style — every fix added or relocated assertions to fail loud at the boundary.
- No nested-if — all changes are flat statements/assertions; verifier-grep returns 0.
- Self-explanatory naming — `task_uuid = str(uuid.uuid4())` is more obvious than the prior float-suffix string.

---

_Fixed: 2026-04-29T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
