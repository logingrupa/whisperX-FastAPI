---
phase: 16
plan: 06
type: execute
wave: 1
depends_on: [16-01]
files_modified:
  - tests/integration/test_migration_smoke.py
autonomous: true
requirements: [VERIFY-08]
tags: [verification, migration, alembic, brownfield, fk-enforcement]
must_haves:
  truths:
    - "Synthetic v1.1 baseline (tasks table, no user_id col) → alembic stamp 0001_baseline → upgrade to 0002 succeeds; tasks rows preserved"
    - "After 0002 upgrade + admin user seeded + UPDATE tasks SET user_id=admin → upgrade to head succeeds; 0003 NOT NULL constraint applies cleanly"
    - "Post-upgrade row count equals pre-upgrade tasks count (no data loss)"
    - "Post-upgrade tasks.user_id IS NOT NULL on every row"
    - "Post-upgrade FK constraints enforce — PRAGMA foreign_keys=ON; deleting referenced user with CASCADE/SET NULL fires"
  artifacts:
    - path: "tests/integration/test_migration_smoke.py"
      provides: "VERIFY-08 — 4 cases (row preservation, user_id assignment, FK enforcement, count parity)"
      min_lines: 200
      contains: "_run_alembic"
  key_links:
    - from: "test_migration_smoke.py"
      to: "tests/integration/_phase16_helpers._run_alembic"
      via: "subprocess invocation with DB_URL env"
      pattern: "_run_alembic\\(\\["
    - from: "_build_v11_baseline helper"
      to: "alembic 0002 upgrade path"
      via: "schema mirror of pre-Phase-10 tasks table"
      pattern: "CREATE TABLE tasks"
---

<objective>
Implement VERIFY-08 migration smoke. Caveman: synthetic v1.1 baseline → alembic stamp 0001 → upgrade to 0002 → seed admin + UPDATE tasks.user_id → upgrade to head → assert row count, NOT NULL, FK enforcement.

Purpose: prove operator-facing migration runbook (Phase 17 OPS-03) executes against a v1.1-shaped DB without data loss and that 0003 NOT NULL constraint applies cleanly.
Output: tests/integration/test_migration_smoke.py (~200 lines).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-CONTEXT.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-RESEARCH.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md

@tests/integration/test_alembic_migration.py
@tests/integration/_phase16_helpers.py
@alembic/versions/0001_baseline.py
@alembic/versions/0002_auth_schema.py
@alembic/versions/0003_tasks_user_id_not_null.py

<interfaces>
<!-- From _phase16_helpers -->
def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]
REPO_ROOT: Path

<!-- Migration sequence (verified per 16-RESEARCH.md Pitfall 8 + STATE.md Phase 10/12) -->
# 1. Build v1.1 tasks table (no user_id col) + N rows
# 2. _run_alembic(["stamp", "0001_baseline"], db_url) — marks current
# 3. _run_alembic(["upgrade", "0002_auth_schema"], db_url) — adds nullable user_id col, all auth tables
# 4. INSERT admin user + UPDATE tasks SET user_id = admin_id
# 5. _run_alembic(["upgrade", "head"], db_url) — applies 0003 NOT NULL pre-flight + alter
# 6. Assert: row count preserved, user_id NOT NULL, FK enforce
```

</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| test process → alembic subprocess | clean env; tmp DB isolated from in-process global engine |
| in-process create_engine → tmp DB | per-assertion fresh engine; no shared cache |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-16-03 | Tampering | global engine contamination | mitigate | subprocess gets isolated env via _run_alembic; assertions create fresh engine on tmp_path DB |
| T-16-04 | Spoofing | migration test passes for wrong reason | mitigate | assert row count BEFORE and AFTER + assert column metadata via inspect() — multi-axis verification |
| T-16-08 (variant) | Tampering | 0003 pre-flight orphan check fires unexpectedly | mitigate | seed admin row + UPDATE tasks.user_id BETWEEN 0002 and head upgrade per Pitfall 8 |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Helpers — _build_v11_baseline + _make_engine + admin user seed</name>
  <files>tests/integration/test_migration_smoke.py</files>
  <read_first>
    - tests/integration/test_alembic_migration.py (full file — primary template)
    - alembic/versions/0001_baseline.py — confirm revision id is "0001_baseline" (or look up exact value)
    - alembic/versions/0002_auth_schema.py — confirm revision id, users table column shape
    - alembic/versions/0003_tasks_user_id_not_null.py — confirm orphan-row pre-flight raises RuntimeError if any tasks.user_id IS NULL
    - app/infrastructure/database/models.py — User model column shape (email, hashed_password, plan_tier, token_version, etc.)
  </read_first>
  <action>
Create file with module docstring: "VERIFY-08 migration smoke — synthetic v1.1 baseline → upgrade head; assert row preservation + tasks.user_id NOT NULL + FK enforcement."

Imports:
```python
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.integration._phase16_helpers import REPO_ROOT, _run_alembic
```

Helpers:

`_make_engine(db_path: Path)`:
```python
return create_engine(
    f"sqlite:///{db_path}",
    connect_args={"check_same_thread": False},
)
```

`_build_v11_baseline(db_path: Path, *, n_tasks: int = 3) -> None`:
- Create tasks table with v1.1 column shape (NO user_id col).
- Mirror columns from app/infrastructure/database/models.py Task ORM minus user_id, minus added Phase-10 columns. Use a CREATE TABLE statement matching v1.1 exactly:
```python
engine = _make_engine(db_path)
with engine.begin() as conn:
    conn.exec_driver_sql(
        "CREATE TABLE tasks ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  uuid TEXT, status TEXT, result TEXT, file_name TEXT,"
        "  url TEXT, callback_url TEXT, audio_duration REAL,"
        "  language TEXT, task_type TEXT, task_params TEXT,"
        "  duration REAL, start_time TEXT, end_time TEXT, error TEXT,"
        "  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,"
        "  progress_percentage INTEGER DEFAULT 0, progress_stage TEXT"
        ")"
    )
    for i in range(n_tasks):
        conn.exec_driver_sql(
            "INSERT INTO tasks (uuid, status, task_type, created_at, updated_at) "
            "VALUES (?, 'pending', 'speech-to-text', "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            (f"legacy-task-{i}",),
        )
engine.dispose()
```
(Direct copy from .planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md `_build_v11_baseline` section.)

NOTE: If existing test_alembic_migration.py uses a slightly different column shape, mirror that one for consistency. The CREATE TABLE must be exactly what alembic 0001_baseline expects to "stamp" against.

`_seed_admin_user_and_assign_tasks(db_path: Path) -> int`:
- Engine + connection → INSERT a users row matching the post-0002 schema (email, hashed_password='$argon2id$dummy', plan_tier='pro', token_version=0, created_at=updated_at='2026-04-29 00:00:00')
- Returns the new admin user_id (lastrowid)
- UPDATE tasks SET user_id = admin_id (every row)
- engine.dispose()
- Use exec_driver_sql for both — no ORM dependency (keeps test self-contained against schema drift):
```python
def _seed_admin_user_and_assign_tasks(db_path: Path) -> int:
    engine = _make_engine(db_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users (email, hashed_password, plan_tier, token_version, created_at, updated_at) "
            "VALUES (?, ?, 'pro', 0, '2026-04-29 00:00:00', '2026-04-29 00:00:00')",
            ("admin@phase16.example.com", "$argon2id$dummy"),
        )
        admin_id = conn.exec_driver_sql("SELECT id FROM users WHERE email = 'admin@phase16.example.com'").scalar()
        conn.exec_driver_sql("UPDATE tasks SET user_id = ?", (admin_id,))
    engine.dispose()
    return int(admin_id)
```

CAVEAT: The exact column list for users may differ; cross-check 0002_auth_schema.py users table create_table call. If columns like `stripe_customer_id` are NOT NULL, omit them (default NULL) or add to the INSERT. Adjust the INSERT statement to include exactly those 0002 NOT-NULL columns + reasonable defaults for nullable ones.

DRT: each helper has one job; reused by multiple tests if needed.
SRP: _build_v11_baseline doesn't seed admin (separate helper); _seed_admin_user_and_assign_tasks doesn't build schema (assumes 0002 applied).
Tiger-style: assert lastrowid resolved (`assert admin_id is not None`).
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_migration_smoke.py --collect-only -q 2>&1 | head -20</automated>
  </verify>
  <done>
    - File created with three helpers
    - pytest collects (no syntax errors)
  </done>
  <acceptance_criteria>
    - `grep -c "def _make_engine\\|def _build_v11_baseline\\|def _seed_admin_user_and_assign_tasks" tests/integration/test_migration_smoke.py` == 3
    - `grep -c "from tests.integration._phase16_helpers import" tests/integration/test_migration_smoke.py` == 1
    - `grep -c "_run_alembic" tests/integration/test_migration_smoke.py` >= 1
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: 4 smoke cases — preservation, user_id assignment, FK enforcement, count parity</name>
  <files>tests/integration/test_migration_smoke.py</files>
  <read_first>
    - tests/integration/test_migration_smoke.py (current state from Task 1)
    - alembic/versions/0001_baseline.py — confirm exact revision identifier (e.g. "0001_baseline" vs "0001_baseline_empty_stamp")
    - alembic/versions/0002_auth_schema.py — confirm revision identifier (e.g. "0002_auth_schema" vs full UUID)
    - tests/integration/test_alembic_migration.py for revision-id usage examples
  </read_first>
  <action>
Append 4 test functions:

```python
@pytest.mark.integration
def test_brownfield_v11_to_head_preserves_task_rows(tmp_path: Path) -> None:
    """v1.1 tasks → 0001 stamp → upgrade head: row count preserved."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=3)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    with engine.connect() as conn:
        row_count = conn.exec_driver_sql("SELECT COUNT(*) FROM tasks").scalar()
    engine.dispose()

    assert row_count == 3, f"row count changed from 3 to {row_count}"


@pytest.mark.integration
def test_brownfield_v11_to_head_assigns_user_id(tmp_path: Path) -> None:
    """Post-upgrade: every tasks row has user_id IS NOT NULL referencing seeded admin."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=5)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    admin_id = _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    with engine.connect() as conn:
        null_count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL"
        ).scalar()
        admin_match_count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?", (admin_id,)
        ).scalar()
    engine.dispose()

    assert null_count == 0, f"{null_count} tasks still have NULL user_id post-upgrade"
    assert admin_match_count == 5, f"expected 5 tasks owned by admin, got {admin_match_count}"


@pytest.mark.integration
def test_brownfield_v11_to_head_user_id_column_not_null(tmp_path: Path) -> None:
    """Post-upgrade: tasks.user_id column is NOT NULL (constraint applied by 0003)."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=2)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    cols = {c["name"]: c for c in inspect(engine).get_columns("tasks")}
    engine.dispose()

    assert "user_id" in cols, f"tasks.user_id missing; cols={list(cols)}"
    assert cols["user_id"]["nullable"] is False, "tasks.user_id must be NOT NULL post-0003"


@pytest.mark.integration
def test_brownfield_fk_constraints_enforced(tmp_path: Path) -> None:
    """Post-upgrade: PRAGMA foreign_keys=ON enforces FK constraints on insert."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=1)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    # SQLAlchemy global engine listener (Phase 10-04) sets PRAGMA foreign_keys=ON.
    # In this test we use a fresh engine without that listener — we must enable manually.
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        # Attempt to INSERT a task referencing a non-existent user_id → FK violation
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(
                "INSERT INTO tasks (uuid, status, task_type, user_id, created_at, updated_at) "
                "VALUES ('orphan-task', 'pending', 'speech-to-text', 99999, "
                "'2026-04-29 00:00:00', '2026-04-29 00:00:00')"
            )
    engine.dispose()
```

DRT: each test repeats the 4-step migration sequence (build → stamp → upgrade-to-0002 → seed-admin → upgrade-to-head). This is intentional — pytest test isolation requires each to start from scratch. Could extract to a fixture, but the duplication is small and the trace is locally readable (tiger-style: each test reads top-to-bottom).

OPTIONAL DRT REFACTOR: extract a `_prepare_migrated_db(tmp_path, *, n_tasks) -> tuple[Path, int]` fixture/helper that returns `(db_path, admin_id)` after the full 5-step setup. Each test becomes 4 lines + 1 prepared call. Worth doing if the file ends up >200 lines.

Tiger-style: every test asserts MORE THAN status (row count, column metadata, IntegrityError type).
SRP: each test has ONE assertion focus (preservation, user_id assignment, NOT NULL constraint, FK enforce).
Self-explanatory names: db_path, admin_id, null_count, cols, row_count.
No nested-if (only `with` context managers, `for` not present, `pytest.raises` is not nesting).

REVISION-AT-EXEC-TIME: After running the 4 tests once, if duplication exceeds the 50-line threshold, refactor to `_prepare_migrated_db` helper. Plan author trusts executor judgment on this.
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_migration_smoke.py -x -q 2>&1 | tail -30</automated>
  </verify>
  <done>
    - 4 cases collected and green
    - Brownfield v1.1 → head migration succeeds
    - Row count preserved
    - tasks.user_id NOT NULL applied
    - FK enforcement verified via deliberate orphan INSERT raising IntegrityError
  </done>
  <acceptance_criteria>
    - `uv run pytest tests/integration/test_migration_smoke.py -q --co 2>&1 | grep -c "::test_"` == 4
    - `uv run pytest tests/integration/test_migration_smoke.py -x -q` exit code 0
    - `grep -c "_run_alembic" tests/integration/test_migration_smoke.py` >= 8 (3 calls × ~3 tests, OR per-test 3 + DRY helper)
    - `grep -c "PRAGMA foreign_keys" tests/integration/test_migration_smoke.py` >= 1
    - `grep -c "IntegrityError" tests/integration/test_migration_smoke.py` >= 1
    - Nested-if invariant: `grep -cE "        if .*:$" tests/integration/test_migration_smoke.py` == 0
  </acceptance_criteria>
</task>

</tasks>

<verification>
- `uv run pytest tests/integration/test_migration_smoke.py -v` → 4 green
- VERIFY-08 closed
- Phase 17 OPS-03 docs (migration runbook) can reference this test as the executable proof-of-runbook
</verification>

<success_criteria>
- 4 cases pass
- Synthetic v1.1 baseline schema mirrors pre-Phase-10 tasks table exactly
- 4-step migration sequence executes (stamp → upgrade-to-0002 → seed-admin → upgrade-to-head)
- 0003 NOT NULL pre-flight passes (because admin user assigned to all tasks before upgrade)
- FK enforcement verified independently via deliberate orphan INSERT
- _run_alembic subprocess pattern matches Plan 10-04 lesson (Windows venv portability)
- Tiger-style: row count, column metadata, IntegrityError all asserted
- No nested-if
</success_criteria>

<output>
After completion, create `.planning/phases/16-verification-cross-user-matrix-e2e/16-06-SUMMARY.md`
</output>
