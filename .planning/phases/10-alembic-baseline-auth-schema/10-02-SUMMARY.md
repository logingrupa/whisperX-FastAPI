---
phase: 10-alembic-baseline-auth-schema
plan: 02
subsystem: database
tags: [sqlalchemy, orm, models, auth, billing-ready, tiger-style, dry-factories]

# Dependency graph
requires:
  - phase: 10-alembic-baseline-auth-schema
    plan: 01
    provides: 0001_baseline migration with tasks table; alembic env wired to Config.DB_URL
provides:
  - 6 new ORM classes (User, ApiKey, Subscription, UsageEvent, RateLimitBucket, DeviceFingerprint) on Base.metadata
  - tasks.user_id Mapped[int | None] FK→users.id ON DELETE SET NULL (named fk_tasks_user_id)
  - DRY datetime factories _created_at_column() / _updated_at_column() — 9 invocations across 7 ORM classes
  - Task.created_at / Task.updated_at now tz-aware at the ORM level (matches post-0002 DB shape)
  - app/infrastructure/database/__init__.py barrel re-exports all 6 new classes
affects: [10-03 0002_auth_schema migration, 10-04 PRAGMA + integration tests, 11-* repository wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DRY column factories at module level — _created_at_column() / _updated_at_column() reused 9 times"
    - "Tiger-style fail-loud module-bottom asserts on every __tablename__ (User..DeviceFingerprint)"
    - "SQLAlchemy 2.x Mapped[T] + mapped_column with comment= on every column (matches Task analog)"
    - "Named FK/CHECK/Index/Unique constraints (fk_<table>_<col>, ck_<table>_<col>, idx_<table>_<col>, uq_<table>_<descr>)"
    - "PEP 604 union syntax for nullables (Mapped[str | None]) — never Optional[T]"
    - "Zero `if` statements in ORM module — flat declarative declarations only"
    - "No `relationship` imported — back-population deferred to Phase 11+ (DRT — don't import what isn't used)"

key-files:
  created: []
  modified:
    - app/infrastructure/database/models.py
    - app/infrastructure/database/__init__.py

key-decisions:
  - "Task.created_at / Task.updated_at migrated to factories in this plan (not Plan 03's batch_alter_table) — ORM matches post-0002 DB shape proactively, single source of truth"
  - "Factory invocations locked: 6 created_at + 3 updated_at = 9 total; RateLimitBucket uses inline last_refill (semantic-different from created_at)"
  - "tasks.user_id added in ORM here (Plan 02), DDL added in Plan 03 — Phase 10 split keeps migration ops mechanical"
  - "relationship() deliberately NOT imported — keeps DRY (no unused imports), keeps Phase 10 surface minimal; Phase 11 wires repository-level joins"
  - "Module-bottom asserts use one assert per class (not a loop) — grep-friendly for verifier and tiger-style fail-fast at module load"

requirements-completed: [SCHEMA-03, SCHEMA-04, SCHEMA-06, SCHEMA-07, SCHEMA-08]

# Metrics
duration: 3min
completed: 2026-04-29
---

# Phase 10 Plan 02: Auth/Billing ORM Models + Task Migration Summary

**Six new ORM classes (User, ApiKey, Subscription, UsageEvent, RateLimitBucket, DeviceFingerprint) added on Base.metadata, tasks.user_id FK declared, Task.created_at/updated_at swapped to DRY tz-aware factories — Base.metadata now enumerates 7 tables, factories invoked 9 times, zero `if` statements, zero `relationship` imports, all 9 named constraints (1 CK + 1 IX + 1 UQ + 6 FK) verified at module load.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-29T04:39:37Z
- **Completed:** 2026-04-29T04:43:05Z
- **Tasks:** 2
- **Files created:** 0
- **Files modified:** 2 (models.py +374 lines net, __init__.py +14 lines net)

## Accomplishments

### ORM Surface (Base.metadata)

Base.metadata now enumerates exactly 7 tables alphabetically:

```python
['api_keys', 'device_fingerprints', 'rate_limit_buckets', 'subscriptions', 'tasks', 'usage_events', 'users']
```

### 6 New ORM Classes

| Class             | __tablename__         | created_at factory | updated_at factory | Constraints (named)                    |
|-------------------|-----------------------|--------------------|--------------------|----------------------------------------|
| User              | users                 | ✓                  | ✓                  | ck_users_plan_tier (CHECK enum)        |
| ApiKey            | api_keys              | ✓                  | —                  | idx_api_keys_prefix (INDEX), fk_api_keys_user_id (FK CASCADE) |
| Subscription      | subscriptions         | ✓                  | ✓                  | fk_subscriptions_user_id (FK CASCADE)  |
| UsageEvent        | usage_events          | ✓                  | —                  | fk_usage_events_user_id, fk_usage_events_task_id (FKs); idempotency_key UNIQUE NOT NULL |
| RateLimitBucket   | rate_limit_buckets    | — (inline last_refill) | —              | bucket_key UNIQUE NOT NULL             |
| DeviceFingerprint | device_fingerprints   | ✓                  | —                  | uq_device_fingerprints_composite (UNIQUE), fk_device_fingerprints_user_id (FK CASCADE) |
| **Task (existing)** | tasks               | ✓ (factory swap)   | ✓ (factory swap)   | fk_tasks_user_id (FK SET NULL, NEW)    |

### Factory Invocation Roster (DRY enforcement)

| Class               | _created_at_column() | _updated_at_column() |
|---------------------|----------------------|----------------------|
| User                | ✓                    | ✓                    |
| ApiKey              | ✓                    | —                    |
| Subscription        | ✓                    | ✓                    |
| UsageEvent          | ✓                    | —                    |
| DeviceFingerprint   | ✓                    | —                    |
| RateLimitBucket     | — (inline)           | —                    |
| Task                | ✓                    | ✓                    |
| **Invocations**     | **6**                | **3**                |

**Total factory invocations: 9** (matches plan's locked factory invocation table verbatim).

### Grep-Verifiable Counts

| Pattern                                | Count | Required |
|----------------------------------------|-------|----------|
| `_created_at_column\|_updated_at_column` | 11    | ≥11 (2 defs + 9 invocations) |
| `= _created_at_column()`               | 6     | =6       |
| `= _updated_at_column()`               | 3     | =3       |
| `DateTime(timezone=True)`              | 11    | ≥9       |
| `^\s*if `                              | 0     | =0       |
| `relationship`                         | 0     | =0       |
| `name="fk_tasks_user_id"`              | 1     | =1       |
| `ondelete="SET NULL"`                  | 1     | =1       |
| `ck_users_plan_tier`                   | 1     | ≥1       |
| `idx_api_keys_prefix`                  | 1     | ≥1       |
| `uq_device_fingerprints_composite`     | 1     | ≥1       |

### Named Constraint Roster (verified via Base.metadata reflection)

- **FKs (6):** `fk_tasks_user_id`, `fk_api_keys_user_id`, `fk_subscriptions_user_id`, `fk_usage_events_user_id`, `fk_usage_events_task_id`, `fk_device_fingerprints_user_id`
- **CHECK (1):** `ck_users_plan_tier` — rejects values outside `('free','trial','pro','team')`
- **INDEX (1):** `idx_api_keys_prefix` ON (`prefix`) — O(log n) bearer prefix lookup
- **UNIQUE (1):** `uq_device_fingerprints_composite` ON (`user_id`, `cookie_hash`, `ua_hash`, `ip_subnet`, `device_id`)

### Tiger-Style Module-Load Invariants

Six module-bottom asserts (one per new __tablename__) fire at import time. Verified by `python -c "import app.infrastructure.database.models"` exiting 0 — drift in any tablename would `AssertionError` immediately.

### Task Class Migration (proactive DB-shape alignment)

- `Task.created_at` and `Task.updated_at` now use `_created_at_column()` / `_updated_at_column()` factories.
- Both columns are now `DateTime(timezone=True)` at the **ORM level** — matches post-0002 DB shape proactively (Plan 03's batch_alter_table is mechanical mirroring, not surprise re-shaping).
- All other Task columns (uuid, status, result, file_name, url, callback_url, audio_duration, language, task_type, task_params, duration, start_time, end_time, error, progress_percentage, progress_stage) preserved verbatim.
- New: `Task.user_id Mapped[int | None]` with named FK `fk_tasks_user_id` ON DELETE SET NULL (nullable until Phase 12 backfill).

## Task Commits

Each task committed atomically:

1. **Task 1: Imports + DRY factories + Task tz-aware migration + tasks.user_id** — `144c9e8` (feat)
2. **Task 2: 6 new ORM classes + tiger-style asserts + __init__.py re-exports** — `9f7c925` (feat)

## Files Modified

- `app/infrastructure/database/models.py` — +374 net lines (109 → 521): added factories, migrated Task to factories, added tasks.user_id, appended User/ApiKey/Subscription/UsageEvent/RateLimitBucket/DeviceFingerprint classes, appended 6 module-bottom tiger-style asserts.
- `app/infrastructure/database/__init__.py` — +14 net lines (29 → 43): barrel re-exports for the 6 new classes; `__all__` updated.

## Decisions Made

- **`relationship()` not imported** — DRY-strict: zero `relationship(...)` calls anywhere in this plan (back-population belongs to Phase 11 repositories where joins live). Importing the symbol now would be dead code.
- **Task migrated to factories in Plan 02 (not Plan 03)** — Plan 03 still has `batch_alter_table()` to ALTER the live DB columns, but the ORM ↔ DB shape is now consistent at the source: factories define `DateTime(timezone=True)` once, both new and existing classes consume them.
- **One assert per class (not a loop)** — six explicit `assert <Class>.__tablename__ == "<expected>"` lines at module bottom. Grep-friendly for the verifier (`grep -c '^assert ' models.py` → 6) and tiger-style (each line is its own fail-loud invariant).
- **String length annotations on hash columns** — `prefix: String(8)`, `hash: String(64)`, `cookie_hash: String(64)`, `ua_hash: String(64)`. SQLite ignores VARCHAR length but documenting the intent (sha256 hex = 64 chars; api-key prefix = 8 chars) helps Plan 03's migration ops emit correct DDL and helps future Postgres migration produce correct types.
- **`server_default` on `plan_tier`, `token_version`, `scopes`** — both Python `default=` (for ORM-side INSERTs without explicit values) AND `server_default=` (for raw SQL or future migrations). Belt-and-suspenders matches the v1.2 spec ("`DEFAULT 'trial'`" in CONTEXT §35).

## Deviations from Plan

None — plan executed exactly as written. Both tasks landed verbatim; all grep gates and runtime assertions passed on first execution.

## Issues Encountered

- **mypy / ruff not installed in venv** — `.venv/Scripts/python.exe -m ruff` and `-m mypy` both report "No module named …". Pre-commit also missing. Plan 10-01 SUMMARY already noted this same environment limitation (it produced clean commits without running these tools). Functional verification (Python import + grep gates + Base.metadata reflection) is the source of truth and all gates pass. Tracking this as a phase-level deferred item: install dev tooling before Phase 16 verifier matrix.

## User Setup Required

None — no schema changes deploy with this plan; Plan 03 emits the actual DDL via Alembic.

## Next Phase Readiness

- **Plan 03 (0002_auth_schema migration):** has the ORM model shapes it needs to mirror as `sa.Column(...)` `op.create_table(...)` ops. Tablename, column shapes, named constraints, FK ondelete strategies — all locked in this plan.
- **Plan 04 (PRAGMA + tests):** has 7 tables to integration-test (`alembic upgrade head` → inspect 7 tables; CHECK rejects invalid plan_tier; idempotency_key rejects duplicates).
- **Phase 11 (repository layer):** can now type-hint `User`, `ApiKey`, `Subscription`, `UsageEvent`, `RateLimitBucket`, `DeviceFingerprint` from `app.infrastructure.database` barrel.
- No blockers. records.db untouched (this plan is ORM-only — no DB writes).

## Self-Check: PASSED

All claimed artifacts verified on disk:
- `app/infrastructure/database/models.py` — 521 lines, 6 new ORM classes, 9 factory invocations, 6 tiger-style asserts ✓
- `app/infrastructure/database/__init__.py` — 6 new re-exports ✓
- `.planning/phases/10-alembic-baseline-auth-schema/10-02-SUMMARY.md` — this file ✓

All claimed commits resolve in git log:
- `144c9e8` (Task 1 feat: factories + Task tz-aware + tasks.user_id) ✓
- `9f7c925` (Task 2 feat: 6 ORM classes + tiger-style + __init__.py) ✓

Runtime verification (executed pre-summary):
- `Base.metadata.tables` enumerates all 7 expected tables ✓
- `Task.__table__.c.created_at.type.timezone is True` ✓
- `Task.__table__.c.updated_at.type.timezone is True` ✓
- `Task.user_id` attribute exists ✓
- `UsageEvent.__table__.c.idempotency_key.unique is True and .nullable is False` ✓
- All 6 named FKs reflect on Base.metadata ✓
- `ck_users_plan_tier`, `idx_api_keys_prefix`, `uq_device_fingerprints_composite` all reflect ✓
- All 6 tiger-style `assert __tablename__ == ...` invariants pass at import time ✓

---
*Phase: 10-alembic-baseline-auth-schema*
*Completed: 2026-04-29*
