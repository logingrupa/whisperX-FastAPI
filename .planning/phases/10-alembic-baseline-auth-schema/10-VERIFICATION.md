---
phase: 10-alembic-baseline-auth-schema
verified: 2026-04-29T05:10:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
gaps: []
deferred: []
human_verification: []
---

# Phase 10: Alembic Baseline + Auth Schema — Verification Report

**Phase Goal:** Schema foundation — Alembic owns migrations, auth/billing/rate-limit tables exist, `tasks.user_id` exists nullable; zero observable behavior change.
**Verified:** 2026-04-29
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                         | Status     | Evidence                                                                                                     |
| --- | ------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------ |
| 1   | Alembic owns migrations (CLI, env.py, history, dependency)   | VERIFIED | `alembic.ini` exists; `alembic/env.py` imports `Config.DB_URL` + `Base.metadata`; `alembic history` shows `<base> -> 0001_baseline -> 0002_auth_schema (head)`; `pyproject.toml` line 30 `"alembic>=1.13.0"` |
| 2   | 6 new tables defined (ORM + migration)                       | VERIFIED | `Base.metadata.tables.keys()` enumerates all 7 (incl. tasks); `0002_auth_schema.py` contains 6 `op.create_table` calls (one per: users, api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints) |
| 3   | tasks.user_id nullable FK with `fk_tasks_user_id ON DELETE SET NULL` | VERIFIED | `Task.user_id` Mapped[int|None] declared models.py:140-145; FK reflected as `name='fk_tasks_user_id'`, `ondelete='SET NULL'`, `nullable=True`; 0002 batch_alter_table block adds it |
| 4   | `Base.metadata.create_all()` removed from app/main.py        | VERIFIED | `grep -c "create_all" app/main.py` returns 0; `grep -rn "Base.metadata.create_all" app/` returns 0 hits |
| 5   | `PRAGMA foreign_keys = ON` enforced via Engine 'connect' listener + module-load assert | VERIFIED | connection.py:32 `@event.listens_for(Engine, "connect")`; line 65 `assert _fk_on == 1`; runtime check returns 1 |
| 6   | `DateTime(timezone=True)` on every datetime column declared in this phase + Task.created_at/updated_at | VERIFIED (with note) | 11 occurrences in models.py; Task.created_at.tz=True, Task.updated_at.tz=True; all 6 new ORM classes use tz-aware datetimes. Note: pre-existing `Task.start_time` and `Task.end_time` remain plain DateTime per plan-locked scope (CONTEXT §62-63 only migrates created_at/updated_at; Plan 02 directs "Do NOT change any other Task column") |
| 7   | `users.plan_tier` CHECK enforced (`ck_users_plan_tier`)      | VERIFIED | models.py:211-214 `CheckConstraint(...)`; 0002 line 61-64 mirrors; integration test `test_check_constraint_rejects_invalid_plan_tier` PASSED |
| 8   | `usage_events.idempotency_key` UNIQUE NOT NULL (`uq_usage_events_idempotency_key`) | VERIFIED | UsageEvent.__table__.c.idempotency_key.unique=True, nullable=False; 0002 line 149-152; integration test `test_unique_constraint_rejects_duplicate_idempotency_key` PASSED |
| 9   | Integration tests pass (≥7 tests covering greenfield + brownfield) | VERIFIED | `pytest tests/integration/test_alembic_migration.py -v -m integration` → 7 passed, 0 failed in 23.06s |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact                                              | Expected                                              | Status     | Details                                              |
| ----------------------------------------------------- | ----------------------------------------------------- | ---------- | ---------------------------------------------------- |
| `alembic.ini`                                         | CLI config; script_location=alembic                   | VERIFIED | `script_location = alembic` line 8                   |
| `alembic/env.py`                                      | Imports Config.DB_URL + Base.metadata; render_as_batch=True both modes | VERIFIED | All imports + 2× render_as_batch=True occurrences    |
| `alembic/versions/0001_baseline.py`                   | revision=0001_baseline; creates tasks                 | VERIFIED | `op.create_table("tasks", ...)` line 30; revision metadata correct |
| `alembic/versions/0002_auth_schema.py`                | down_revision=0001_baseline; 6 create_table; 2 batch_alter_table | VERIFIED | All 6 tables grep-match; 21 DateTime(timezone=True) occurrences |
| `app/infrastructure/database/models.py`               | 6 new ORM classes + Task.user_id + factories          | VERIFIED | 521 lines; 6 new classes; 9 factory invocations; 0 if statements; 0 relationship imports |
| `app/infrastructure/database/__init__.py`             | Re-exports new ORM classes                            | VERIFIED | All 6 names + Base, Task in `__all__`                |
| `app/infrastructure/database/connection.py`           | PRAGMA listener + module-load assert                  | VERIFIED | listener line 32; assert line 65                     |
| `app/main.py`                                         | No create_all line; Base import preserved             | VERIFIED | grep create_all=0; Base.metadata.tables.values() preserved line 78 |
| `tests/integration/test_alembic_migration.py`         | ≥7 pytest cases; @pytest.mark.integration             | VERIFIED | 7 tests, all PASS; @pytest.mark.integration on class |
| `pyproject.toml`                                      | alembic>=1.13.0 in dependencies                       | VERIFIED | Line 30                                              |

### Key Link Verification

| From                           | To                              | Via                                                       | Status | Details                                                |
| ------------------------------ | ------------------------------- | --------------------------------------------------------- | ------ | ------------------------------------------------------ |
| alembic/env.py                 | app.core.config.Config.DB_URL   | `config.set_main_option("sqlalchemy.url", Config.DB_URL)` | WIRED  | env.py line 21                                         |
| alembic/env.py                 | Base.metadata                   | `target_metadata = Base.metadata`                         | WIRED  | env.py line 26                                         |
| 0002_auth_schema.upgrade()     | tasks.user_id FK → users.id    | batch_op.create_foreign_key("fk_tasks_user_id", ...)      | WIRED  | 0002 line 199-205                                      |
| connection.py engine           | PRAGMA foreign_keys=ON          | `@event.listens_for(Engine, "connect")` + cursor exec     | WIRED  | listener line 32-56; runtime returns 1                 |
| app/main.py                    | (no longer) create_all          | line removed                                              | WIRED  | grep returns 0                                         |
| ApiKey/Subscription/UsageEvent/DeviceFingerprint.user_id | users.id     | `ForeignKey("users.id", ondelete="CASCADE", name="fk_<table>_user_id")` | WIRED | All 5 named FKs reflect on Base.metadata; CASCADE confirmed in 0002 |
| Task.user_id                   | users.id                        | `ForeignKey("users.id", ondelete="SET NULL", name="fk_tasks_user_id")` | WIRED | reflected; ondelete=SET NULL                           |

### Data-Flow Trace (Level 4)

Schema-only phase — no runtime data flow. Skipped per Step 4b ("not applicable for utilities or configs").

### Behavioral Spot-Checks

| Behavior                                       | Command                                                                                              | Result                                                          | Status |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------ |
| App boots cleanly                              | `python -c "import app.main"`                                                                        | exit 0; "boot ok" printed                                       | PASS |
| Module-load assert holds (PRAGMA=1)            | `python -c "import app.infrastructure.database.connection"`                                          | exit 0; no AssertionError                                       | PASS |
| ORM Base.metadata enumerates 7 tables          | `python -c "from app.infrastructure.database.models import Base; print(sorted(Base.metadata.tables.keys()))"` | `['api_keys', 'device_fingerprints', 'rate_limit_buckets', 'subscriptions', 'tasks', 'usage_events', 'users']` | PASS |
| Alembic chain intact                           | `python -m alembic history`                                                                          | `<base> -> 0001_baseline -> 0002_auth_schema (head)`            | PASS |
| Runtime PRAGMA foreign_keys = 1                | `engine.connect().exec_driver_sql('PRAGMA foreign_keys').scalar()`                                  | `1`                                                             | PASS |
| Integration suite passes                       | `pytest tests/integration/test_alembic_migration.py -v -m integration`                              | 7 passed, 1 unrelated warning                                   | PASS |
| Task.user_id FK shape matches spec             | introspect `Task.__table__.foreign_keys`                                                            | `name=fk_tasks_user_id, ondelete=SET NULL, nullable=True`       | PASS |
| UsageEvent.idempotency_key UNIQUE NOT NULL     | introspect column                                                                                    | `unique=True, nullable=False`                                   | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description                                                                          | Status      | Evidence                                                                      |
| ----------- | ----------- | ------------------------------------------------------------------------------------ | ----------- | ----------------------------------------------------------------------------- |
| SCHEMA-01   | 10-01, 10-04 | Alembic migrations as single source of truth                                        | SATISFIED | alembic CLI installed; create_all removed from main.py; chain present         |
| SCHEMA-02   | 10-01       | Baseline migration mirrors existing tasks                                            | SATISFIED | 0001_baseline.py creates 19-col tasks table; brownfield-preserves test PASS   |
| SCHEMA-03   | 10-02, 10-03 | 6 new tables (users, api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints) | SATISFIED | All 6 ORM classes registered; 6 op.create_table calls; greenfield test asserts exact 8-table set |
| SCHEMA-04   | 10-02, 10-03 | tasks.user_id nullable FK to users.id                                               | SATISFIED | Task.user_id Mapped[int\|None]; named FK reflects; integration test asserts column + named FK |
| SCHEMA-05   | 10-04       | PRAGMA foreign_keys=ON via SQLAlchemy event listener                                | SATISFIED | listener registered; module-load assert; runtime returns 1; integration test PASS |
| SCHEMA-06   | 10-02, 10-03 | DateTime(timezone=True) for every datetime column                                   | SATISFIED (locked scope) | 11 tz-aware in models.py; 21 in 0002. NOTE: Task.start_time/end_time remain plain DateTime — explicitly out of scope per CONTEXT §62-63 ("Existing tasks.created_at/updated_at migrated") and Plan 02 ("Do NOT change any other Task column"). REQUIREMENTS.md marks SCHEMA-06 Complete. |
| SCHEMA-07   | 10-02, 10-03 | users.plan_tier CHECK + cancelled_at + stripe_customer_id UNIQUE                    | SATISFIED | ck_users_plan_tier present; subscriptions.cancelled_at present; users.stripe_customer_id unique=True |
| SCHEMA-08   | 10-02, 10-03 | usage_events.idempotency_key UNIQUE NOT NULL                                        | SATISFIED | unique=True, nullable=False; uq_usage_events_idempotency_key named; UNIQUE-fire test PASS |

All 8 phase-10 requirements (SCHEMA-01 through SCHEMA-08) accounted for. None orphaned.

### Anti-Patterns Found

| File                                              | Line | Pattern                       | Severity | Impact                                   |
| ------------------------------------------------- | ---- | ----------------------------- | -------- | ---------------------------------------- |
| (none — clean across all modified files)          | —    | —                             | —        | —                                        |

Specifically verified absent:
- 0 `if` statements in `app/infrastructure/database/models.py` (acceptance gate met)
- 0 `relationship` imports in models.py (DRY: not yet needed)
- 0 `create_all` references in app/ tree
- 1 guard-only `if` in connection.py (early-return for non-SQLite drivers — acceptance allows this single guard)
- 0 nested-if patterns anywhere in modified files

### Human Verification Required

None. All checks programmatic; greenfield + brownfield migration paths exercised by automated integration suite.

### Gaps Summary

No gaps. Phase 10 goal achieved:
- Alembic owns migrations end-to-end (CLI + env.py + 2-revision chain).
- All 6 new tables exist in ORM and DDL.
- tasks.user_id nullable FK present (named, ON DELETE SET NULL).
- create_all removed from boot path.
- PRAGMA foreign_keys=ON enforced and asserted.
- Tz-aware datetimes everywhere within plan-locked scope.
- CHECK + UNIQUE constraints fire (verified by integration tests).
- All 8 SCHEMA-* requirements marked Complete in REQUIREMENTS.md.
- App boots cleanly; observable behavior unchanged (per phase mandate).

### Out-of-Phase Observation (Informational, Not a Gap)

`app/main.py` working tree contains pre-existing dirty modifications unrelated to Phase 10:
- Line 30: `from app.core.auth import BearerAuthMiddleware` (added)
- Line 168: `app.add_middleware(BearerAuthMiddleware)` (added)
- Untracked: `app/core/auth.py`

These changes belong to a different (likely Phase 11/MID-*) workstream. Plan 04 deviation #2 documents this — `git apply --cached` was used to commit ONLY the create_all removal, leaving the BearerAuthMiddleware diff untouched in the working tree. Out of scope for Phase 10. NOT a gap; flagged here so Phase 11 owner can decide whether to absorb or revert.

---

_Verified: 2026-04-29T05:10:00Z_
_Verifier: Claude (gsd-verifier)_
