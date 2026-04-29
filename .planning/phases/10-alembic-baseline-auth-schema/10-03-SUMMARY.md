---
phase: 10-alembic-baseline-auth-schema
plan: 03
subsystem: database
tags: [alembic, migration, sqlite, ddl, batch-alter-table, named-constraints, tiger-style]

# Dependency graph
requires:
  - phase: 10-alembic-baseline-auth-schema
    plan: 01
    provides: 0001_baseline migration creating tasks (19 cols); alembic env wired to Config.DB_URL
  - phase: 10-alembic-baseline-auth-schema
    plan: 02
    provides: 6 ORM model shapes locked (User..DeviceFingerprint); Task.user_id Mapped declared; named constraints registered on Base.metadata
provides:
  - alembic/versions/0002_auth_schema.py — chained head revision (down_revision=0001_baseline)
  - DDL upgrade path: 6 op.create_table calls (users, api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints)
  - DDL upgrade path: 1 op.create_index (idx_api_keys_prefix)
  - DDL upgrade path: 1 batch_alter_table block on tasks (add user_id FK + alter created_at/updated_at to tz-aware)
  - DDL downgrade path: 1 batch_alter_table reversal + 6 op.drop_table + 1 op.drop_index — fully reversible
  - Named constraint roster: 6 FK + 1 CK + 1 IX + 4 UQ (10 named at the migration layer)
  - Greenfield smoke verified: alembic upgrade head produces exactly 8 tables (alembic_version + 7)
  - Brownfield-ready: all tasks ALTERs use op.batch_alter_table (SQLite-safe)
  - Runtime fire-tests verified: ck_users_plan_tier rejects 'invalid_tier'; uq_usage_events_idempotency_key rejects duplicate insert
affects: [10-04 PRAGMA listener + integration tests, 11-* repository wiring, 17-ops-runbook]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Named constraints throughout: fk_<table>_<col>, ck_<table>_<col>, idx_<table>_<col>, uq_<table>_<descr>"
    - "Single-line op.create_table(\"<name>\", ...) opener — keeps grep gates single-line"
    - "All tasks ALTERs wrapped in op.batch_alter_table (SQLite limited ALTER TABLE)"
    - "Inline sa.UniqueConstraint(...) inside op.create_table — predictable named DDL"
    - "Server-side defaults (server_default=) for plan_tier, token_version, scopes — works for raw migration INSERTs"
    - "Zero `if` statements in migration (flat declarative ops only)"
    - "FK ondelete strategy: CASCADE for owned rows; SET NULL for tasks.user_id (orphans preserved)"

key-files:
  created:
    - alembic/versions/0002_auth_schema.py
  modified: []

key-decisions:
  - "Single-line op.create_table opener form — `op.create_table(\"users\",` followed by columns on next lines. Functionally identical to multi-line opener but grep-friendly for the plan's literal-string acceptance gates (same fix Plan 10-01 used)."
  - "Docstring rephrased to avoid literal `op.create_table` text — keeps grep -c \"op.create_table\" at exactly 6 (matching the 6 tables created), no docstring inflation."
  - "21 DateTime(timezone=True) occurrences — far above the ≥12 required minimum (every datetime column tz-aware in both upgrade and downgrade alter_column type_= positions)."
  - "Migration downgrade order: tasks revert FIRST (drop FK + drop user_id col + revert datetime types), THEN drop 6 tables in reverse-FK order (device_fingerprints → users last). Avoids dangling FK references during table drops."
  - "task_id FK on usage_events does NOT use ondelete=CASCADE — audit-trail rows survive even if originating task row is later deleted (CONTEXT §38)."

requirements-completed: [SCHEMA-03, SCHEMA-04, SCHEMA-06, SCHEMA-07, SCHEMA-08]

# Metrics
duration: 2min
completed: 2026-04-29
---

# Phase 10 Plan 03: 0002_auth_schema Migration Summary

**Alembic 0002_auth_schema revision authored verbatim from plan: 6 new tables (users, api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints) + tasks.user_id FK + tasks tz-aware datetime ALTER — all named constraints in place, greenfield smoke passes (8 tables created, 8 tables expected), CHECK + UNIQUE constraints fire correctly, downgrade reverses cleanly to baseline shape.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-29T04:46:29Z
- **Completed:** 2026-04-29T04:48:42Z
- **Tasks:** 1
- **Files created:** 1 (alembic/versions/0002_auth_schema.py — 246 lines)
- **Files modified:** 0

## Accomplishments

### Migration Surface (alembic chain)

```
<base> -> 0001_baseline -> 0002_auth_schema (head)
```

Verified via `alembic history`:
```
0001_baseline -> 0002_auth_schema (head), auth_schema — adds 6 new tables and tasks.user_id FK; migrates tasks tz-aware datetimes.
<base> -> 0001_baseline, baseline — creates the tasks table matching the current ORM shape.
```

### Ops Roster

| Op                   | Count | Locations |
|----------------------|-------|-----------|
| op.create_table      | 6     | users, api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints (upgrade) |
| op.create_index      | 1     | idx_api_keys_prefix (upgrade) |
| op.batch_alter_table | 2     | tasks (upgrade alter), tasks (downgrade revert) |
| op.drop_table        | 6     | downgrade reverse-FK order |
| op.drop_index        | 1     | idx_api_keys_prefix (downgrade) |

### Named Constraint Roster

| Type   | Name                                       | Table                | Columns                                                  |
|--------|--------------------------------------------|----------------------|----------------------------------------------------------|
| FK     | fk_tasks_user_id                           | tasks                | user_id → users.id (ON DELETE SET NULL)                  |
| FK     | fk_api_keys_user_id                        | api_keys             | user_id → users.id (ON DELETE CASCADE)                   |
| FK     | fk_subscriptions_user_id                   | subscriptions        | user_id → users.id (ON DELETE CASCADE)                   |
| FK     | fk_usage_events_user_id                    | usage_events         | user_id → users.id (ON DELETE CASCADE)                   |
| FK     | fk_usage_events_task_id                    | usage_events         | task_id → tasks.id (no cascade — audit trail)            |
| FK     | fk_device_fingerprints_user_id             | device_fingerprints  | user_id → users.id (ON DELETE CASCADE)                   |
| CHECK  | ck_users_plan_tier                         | users                | plan_tier IN ('free','trial','pro','team')               |
| INDEX  | idx_api_keys_prefix                        | api_keys             | (prefix) — bearer prefix lookup                          |
| UNIQUE | uq_users_email                             | users                | (email)                                                  |
| UNIQUE | uq_users_stripe_customer_id                | users                | (stripe_customer_id)                                     |
| UNIQUE | uq_subscriptions_stripe_subscription_id    | subscriptions        | (stripe_subscription_id)                                 |
| UNIQUE | uq_usage_events_idempotency_key            | usage_events         | (idempotency_key)                                        |
| UNIQUE | uq_rate_limit_buckets_bucket_key           | rate_limit_buckets   | (bucket_key)                                             |
| UNIQUE | uq_device_fingerprints_composite           | device_fingerprints  | (user_id, cookie_hash, ua_hash, ip_subnet, device_id)    |

**Total named constraints: 14** (6 FK + 1 CK + 1 IX + 6 UQ).

### Static-Grep Verification (all gates pass)

| Pattern                                                       | Count | Required        | Status |
|---------------------------------------------------------------|-------|-----------------|--------|
| `revision: str = "0002_auth_schema"`                          | 1     | =1              | PASS   |
| `down_revision: Union\[str, None\] = "0001_baseline"`         | 1     | =1              | PASS   |
| `op.create_table`                                             | 6     | =6              | PASS   |
| `op.batch_alter_table`                                        | 2     | =2              | PASS   |
| `DateTime(timezone=True)`                                     | 21    | ≥12             | PASS   |
| `^if \|^    if \|^        if `                                | 0     | =0              | PASS   |
| `if .*:.*if .*:.*if`                                          | 0     | =0              | PASS   |
| `op.create_table("users"`                                     | 1     | ≥1              | PASS   |
| `op.create_table("api_keys"`                                  | 1     | ≥1              | PASS   |
| `op.create_table("subscriptions"`                             | 1     | ≥1              | PASS   |
| `op.create_table("usage_events"`                              | 1     | ≥1              | PASS   |
| `op.create_table("rate_limit_buckets"`                        | 1     | ≥1              | PASS   |
| `op.create_table("device_fingerprints"`                       | 1     | ≥1              | PASS   |
| `ck_users_plan_tier`                                          | ≥1    | ≥1              | PASS   |
| `idx_api_keys_prefix`                                         | ≥1    | ≥1              | PASS   |
| `uq_device_fingerprints_composite`                            | ≥1    | ≥1              | PASS   |
| `uq_usage_events_idempotency_key`                             | ≥1    | ≥1              | PASS   |
| `fk_tasks_user_id`                                            | ≥1    | ≥1              | PASS   |
| `ondelete="SET NULL"`                                         | ≥1    | ≥1              | PASS   |

### Runtime Smoke Verification (executed pre-summary)

Executed against tmp SQLite DB (`./tmp_p10_03_smoke.db`, cleaned up post-run):

**1. Greenfield upgrade head** — runs 0001_baseline + 0002_auth_schema:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_baseline
INFO  [alembic.runtime.migration] Running upgrade 0001_baseline -> 0002_auth_schema
```

**2. Table set verification** — `inspect(engine).get_table_names()` returns:
```python
['alembic_version', 'api_keys', 'device_fingerprints', 'rate_limit_buckets',
 'subscriptions', 'tasks', 'usage_events', 'users']
```
Matches expected set (alembic_version + 7 tables) — `MATCH: True`.

**3. tasks.user_id verification** — column added with named FK ondelete=SET NULL:
```python
{'name': 'fk_tasks_user_id', 'constrained_columns': ['user_id'],
 'referred_table': 'users', 'referred_columns': ['id'],
 'options': {'ondelete': 'SET NULL'}}
```

**4. CHECK constraint fires:**
```
sqlite3.IntegrityError: CHECK constraint failed: ck_users_plan_tier
```
Triggered by `INSERT INTO users (..., plan_tier='invalid_tier', ...)`.

**5. UNIQUE constraint fires:**
```
sqlite3.IntegrityError: UNIQUE constraint failed: usage_events.idempotency_key
```
Triggered by duplicate `INSERT INTO usage_events (..., idempotency_key='k1', ...)`.

**6. Downgrade smoke** — `alembic downgrade -1` from 0002 returns:
```
INFO  [alembic.runtime.migration] Running downgrade 0002_auth_schema -> 0001_baseline
AFTER_DOWNGRADE: ['alembic_version', 'tasks']
MATCH_BASELINE: True
tasks.user_id removed: True
```

**Note:** Per plan output spec, runtime upgrade/downgrade/CHECK/UNIQUE assertions are formally captured in Plan 04 pytest. This plan ships static-grep gates only; the smoke runs above are evidence-only confirmation that the migration is fully functional today.

## Task Commits

1. **Task 1: Author alembic/versions/0002_auth_schema.py** — `832e7c8` (feat)

## Files Created

- `alembic/versions/0002_auth_schema.py` — 246 lines, chained head revision, 6 op.create_table + 2 op.batch_alter_table + 1 op.create_index, all named constraints, fully reversible downgrade.

## Decisions Made

- **Single-line op.create_table opener (`op.create_table("users",`)** — Plan acceptance gate `grep -q 'op.create_table("users"'` requires the table-name string on the same physical line as the function call. Functionally identical to multi-line form, both produce the same DDL. Same fix Plan 10-01 applied for the baseline revision.
- **Docstring `op.create_table` reference rephrased** — original verbatim text from the plan included "op.create_table" inside the docstring. The plan's grep gate `grep -c "op.create_table"` requires exactly 6 hits (one per table). The docstring occurrence pushed count to 7. Reworded to "create-table call" (intent preserved, grep gate satisfied).
- **uq_users_email + uq_users_stripe_customer_id named explicitly in migration** — ORM models.py uses `unique=True` per-column, but the migration uses inline `sa.UniqueConstraint(name="uq_users_email")` for predictable named DDL (downgrade reversibility + verifier reflection).
- **task_id FK on usage_events deliberately lacks ondelete=CASCADE** — usage events are audit-trail rows; deleting a task should not erase the billing record (CONTEXT §38). Confirmed in code; FK without `ondelete=` defaults to NO ACTION.
- **Downgrade order: tasks ALTER first, then drop 6 tables in reverse-FK order** — fk_tasks_user_id must be dropped before users table is dropped, else SQLite recreate-table-copy-data sequence (render_as_batch) would fail. Verified by clean downgrade smoke run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Collapsed `op.create_table(` multi-line opener to single-line `op.create_table("<name>",` form**
- **Found during:** Initial grep gate run after writing the file verbatim per the plan's literal Python.
- **Issue:** Plan's verbatim revision body has `op.create_table(` on one line and `"<name>",` on the next. Plan acceptance criteria require `grep -q 'op.create_table("users"'` etc. for 6 separate tables — single-line greps that fail when the table name is on the next physical line. Identical pattern to Plan 10-01 deviation 2.
- **Fix:** Rewrote 6 `op.create_table(` opener lines as `op.create_table("<name>",` (single-line). Columns continue indented on subsequent lines. Functionally identical Python; grep-checkable now.
- **Files modified:** `alembic/versions/0002_auth_schema.py` (6 opener lines)
- **Verification:** All 6 single-line table-name greps now pass; AST parses cleanly; `alembic upgrade head` runs without error.
- **Committed in:** `832e7c8` (Task 1 commit)

**2. [Rule 3 — Blocking] Reworded module docstring to avoid literal `op.create_table` text**
- **Found during:** Initial grep gate run after writing the file verbatim per the plan's literal Python.
- **Issue:** Plan's verbatim docstring (line 20 in plan-supplied content) contained the phrase "each table is one flat op.create_table call". Plan acceptance gate `grep -c "op.create_table" alembic/versions/0002_auth_schema.py` requires exactly `6` (one per table created). The docstring occurrence inflated count to `7`. Same pattern as Plan 10-01 deviation 1 (env.py docstring vs `render_as_batch=True` count).
- **Fix:** Reworded docstring line to "each table is one flat create-table call" — intent preserved (DRY = each table gets a single flat declarative call); literal grep-targeted string removed from docstring; code-body usage untouched.
- **Files modified:** `alembic/versions/0002_auth_schema.py` (line 20 — docstring only)
- **Verification:** `grep -c "op.create_table" …` → 6 (acceptance gate passes).
- **Committed in:** `832e7c8` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both blocking grep-gate adjustments — same plan-internal contradiction class as Plan 10-01).
**Impact on plan:** Zero scope creep, zero behavioral change. Both fixes are layout-only adjustments to satisfy the plan's own static-grep acceptance gates without altering functional intent. Migration runs identically to the verbatim plan body.

## Issues Encountered

- **ruff not installed in venv** — `.venv/Scripts/python.exe -m ruff` reports "No module named ruff"; system `ruff` also unavailable. Plan 10-01 + 10-02 already documented this same environment limitation. AST parse + alembic dry-run smoke verify the file is syntactically + semantically clean. Linting will be re-asserted in Phase 16 verifier matrix once dev tooling is installed.

## User Setup Required

None — migration ships as a file in source control. Operator runs (Phase 17 runbook):
1. Backup `records.db`
2. `alembic stamp 0001_baseline` (brownfield only — already on disk for v1.1 deployments)
3. `alembic upgrade head` (runs 0002_auth_schema → adds 6 tables + tasks.user_id)

## Next Phase Readiness

- **Plan 04 (PRAGMA listener + integration tests):** has the migration in place. Plan 04's pytest fixtures will exercise `alembic upgrade head` against tmp SQLite + records.db copy and assert the runtime CHECK/UNIQUE behaviors that this plan smoke-verified ad-hoc.
- **Phase 11 (repository layer):** ORM models (Plan 02) + DDL (this plan) now agree on schema shape — repositories can target either ORM-via-Session or raw SQLAlchemy Core safely.
- **Phase 12 (backfill tasks.user_id):** has the nullable FK in place; backfill script can populate the column then alter to NOT NULL via a future migration.
- No blockers. records.db untouched (smoke ran against tmp DB only, cleaned up post-run).

## Self-Check: PASSED

All claimed artifacts verified on disk:
- `alembic/versions/0002_auth_schema.py` (246 lines) ✓
- `.planning/phases/10-alembic-baseline-auth-schema/10-03-SUMMARY.md` (this file) ✓

All claimed commits resolve in git log:
- `832e7c8` (Task 1 feat: 0002_auth_schema migration) ✓

Static + runtime evidence collected pre-summary:
- 6 op.create_table, 2 op.batch_alter_table, 21 DateTime(timezone=True), 0 if statements ✓
- Each of 6 table names matches single-line `op.create_table("<name>",` grep ✓
- All 5 plan-required named constraints present (ck_users_plan_tier, idx_api_keys_prefix, uq_device_fingerprints_composite, uq_usage_events_idempotency_key, fk_tasks_user_id) ✓
- AST parses cleanly (`python -c "import ast; ast.parse(...)"` → AST_PARSE_OK) ✓
- `alembic history` shows `<base> -> 0001_baseline -> 0002_auth_schema (head)` ✓
- Greenfield `alembic upgrade head` produces exactly 8 tables (alembic_version + 7) ✓
- `ck_users_plan_tier` rejects 'invalid_tier' (sqlite3.IntegrityError) ✓
- `uq_usage_events_idempotency_key` rejects duplicate insert (sqlite3.IntegrityError) ✓
- `alembic downgrade -1` returns DB to baseline shape; tasks.user_id removed ✓

---
*Phase: 10-alembic-baseline-auth-schema*
*Completed: 2026-04-29*
