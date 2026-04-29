---
phase: 10-alembic-baseline-auth-schema
plan: 01
subsystem: database
tags: [alembic, sqlite, migrations, sqlalchemy, ddl, baseline]

# Dependency graph
requires:
  - phase: 09-resilience-and-polish
    provides: stable v1.1 backend baseline (records.db tasks table = 460 rows)
provides:
  - Alembic CLI installed and resolvable in .venv (alembic 1.17.0)
  - alembic.ini with empty sqlalchemy.url (overridden by env.py)
  - alembic/env.py wired to Config.DB_URL + Base.metadata, render_as_batch=True
  - alembic/versions/0001_baseline.py creating tasks table (19 cols, ORM-mirror)
  - Greenfield path: alembic upgrade head creates alembic_version + tasks
  - Brownfield path: alembic stamp 0001_baseline marks records.db at chain head
    without touching the 460 existing rows
affects: [10-02 PRAGMA listener, 10-03 auth_schema migration, 10-04 connection hygiene, 17-ops-runbook]

# Tech tracking
tech-stack:
  added: [alembic>=1.13.0]
  patterns:
    - "Alembic env.py imports DB URL from app.core.config.Config — single source of truth"
    - "render_as_batch=True in both offline + online modes (SQLite-safe ALTER)"
    - "Numbered revision filenames (0001_baseline.py) — deterministic for ops runbook"

key-files:
  created:
    - alembic.ini
    - alembic/env.py
    - alembic/script.py.mako
    - alembic/README
    - alembic/versions/0001_baseline.py
  modified:
    - pyproject.toml

key-decisions:
  - "Alembic >=1.13.0 (matches project's >= pinning style for libs that move fast)"
  - "Baseline mirrors current ORM Task verbatim (plain DateTime, nullable=True on uuid/status/task_type) — Plan 03 alters tz-awareness"
  - "Filename 0001_baseline.py (no slug) — keeps ops runbook commands deterministic"
  - "alembic.ini sqlalchemy.url left empty — env.py.set_main_option is the only writer"

patterns-established:
  - "Migration revision header pattern: revision/down_revision/branch_labels/depends_on as typed module constants"
  - "op.create_table single-line opener: op.create_table(\"<name>\", ...) — keeps grep checks single-line"
  - "Baseline-stamp brownfield pattern: existing DBs with target table get stamp + chain join, no upgrade re-runs creates"

requirements-completed: [SCHEMA-01, SCHEMA-02]

# Metrics
duration: 5min
completed: 2026-04-29
---

# Phase 10 Plan 01: Alembic Baseline + tasks-Table Revision Summary

**Alembic 1.17.0 wired to Config.DB_URL with 0001_baseline revision creating the 19-column tasks table — greenfield upgrade head succeeds, brownfield stamp on records.db keeps all 460 rows intact.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-29T04:31:33Z
- **Completed:** 2026-04-29T04:36:17Z
- **Tasks:** 3
- **Files created:** 5 (alembic.ini, alembic/env.py, alembic/script.py.mako, alembic/README, alembic/versions/0001_baseline.py)
- **Files modified:** 1 (pyproject.toml)

## Accomplishments

- Alembic CLI resolves end-to-end in .venv (`alembic --version` → 1.17.0)
- env.py sources DB_URL from `app.core.config.Config.DB_URL` (single source of truth — zero duplication anywhere under `alembic/`)
- `render_as_batch=True` set in both offline + online modes (SQLite ALTER-safe)
- 0001_baseline.upgrade() creates the tasks table mirroring the ORM Task class verbatim (19 columns, types, nullability, server_default for progress_percentage)
- 0001_baseline.downgrade() drops tasks cleanly — both directions reversible
- Greenfield smoke (sqlite:///./tmp_alembic_smoke.db): `alembic upgrade head` → tables `[alembic_version, tasks]` created, version_num='0001_baseline'; downgrade base → tasks dropped
- Brownfield smoke (copy of records.db, 460 rows pre-stamp): `alembic stamp 0001_baseline` → version_num='0001_baseline', task count still 460, zero data mutation

## Task Commits

Each task committed atomically:

1. **Task 1: Add alembic to pyproject.toml dependencies** — `6611353` (chore)
2. **Task 2: Generate Alembic scaffolding (alembic.ini + env.py + script.py.mako)** — `92a3d4f` (feat)
3. **Task 3: Create baseline revision creating tasks table** — `c0055d3` (feat)

## Files Created/Modified

- `alembic.ini` — CLI config; `script_location = alembic`; `sqlalchemy.url =` (empty, overridden by env.py); rest is stock Alembic init output
- `alembic/env.py` — Migration runner; imports `Config.DB_URL` and `Base.metadata`; `render_as_batch=True` in offline + online modes
- `alembic/script.py.mako` — Stock Alembic revision template (untouched)
- `alembic/README` — Stock Alembic init artifact
- `alembic/versions/0001_baseline.py` — Baseline revision; `revision="0001_baseline"`, `down_revision=None`; upgrade creates tasks (19 cols), downgrade drops
- `pyproject.toml` — Added `"alembic>=1.13.0",` to `dependencies = [...]`

## Decisions Made

- **Filename `0001_baseline.py` (no slug)** — Plan 17 ops runbook will reference this exact filename; deterministic operator commands matter more than autogen slug.
- **Plain `sa.DateTime()` (no tz=True) in baseline** — Brownfield records.db has plain DATETIME columns. Faithful mirror keeps `alembic stamp 0001_baseline` idempotent. Plan 03's 0002 promotes to `DateTime(timezone=True)` via batch_alter_table.
- **`nullable=True` on `uuid`/`status`/`task_type`** — Existing ORM `Mapped[T]` defaults to nullable=True for non-PK columns; baseline mirrors that to avoid stamp-time CHECK conflicts with possibly-NULL legacy rows.
- **alembic.ini `sqlalchemy.url =` empty** — env.py is the only configured writer of this key (`config.set_main_option`). DRY enforcement: URL exists in `app/core/config.py` and nowhere else.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Adjusted env.py docstring to satisfy grep counts**
- **Found during:** Task 2 (env.py creation)
- **Issue:** Plan's verbatim docstring text contained the literal strings `render_as_batch=True` and `target_metadata = Base.metadata`. The plan's own acceptance criteria required `grep -c "render_as_batch=True" alembic/env.py` to return exactly `2` and `grep -c "target_metadata = Base.metadata"` to return exactly `1`. Including the verbatim docstring text plus the two code-body uses produced counts of 3 and 2 — failing the grep gates.
- **Fix:** Reworded the docstring lines to "The target metadata points at Base.metadata" and "Batch-mode rendering is mandatory" — preserves intent, drops the literal grep-targeted strings from the docstring, leaves code-body usage untouched.
- **Files modified:** `alembic/env.py` (docstring only — lines 4-5)
- **Verification:** Re-ran greps → 2 and 1 (acceptance gates pass). All other env.py code unchanged.
- **Committed in:** `92a3d4f` (Task 2 commit)

**2. [Rule 3 — Blocking] Collapsed `op.create_table(\n        "tasks",` to single-line opener**
- **Found during:** Task 3 (baseline revision)
- **Issue:** Plan's verbatim revision body had `op.create_table(` on one line and `"tasks",` on the next. Plan acceptance required `grep -c 'op.create_table("tasks"' alembic/versions/0001_baseline.py` to return `1` — a single-line grep.
- **Fix:** Wrote opener as `op.create_table("tasks",` on one line; columns continue on subsequent lines with the standard 8-space indent. Functionally identical to the plan's literal Python; grep-checkable now.
- **Files modified:** `alembic/versions/0001_baseline.py` (line 30)
- **Verification:** `grep -c 'op.create_table("tasks"' …` → 1; `alembic upgrade head` against tmp DB still creates the 19-column table.
- **Committed in:** `c0055d3` (Task 3 commit)

**3. [Rule 1 — Bug] Set `script_location = alembic` (not the Alembic-1.17 default `%(here)s/alembic`)**
- **Found during:** Task 2 (alembic.ini customization)
- **Issue:** Alembic 1.17 init wrote `script_location = %(here)s/alembic` by default. Plan must_haves frontmatter specified `contains: "script_location = alembic"` — a literal-string contains check. The %(here)s prefix would not match.
- **Fix:** Edited line 8 to `script_location = alembic` (relative-path form; works because alembic CLI is always invoked from repo root).
- **Files modified:** `alembic.ini` (line 8 only)
- **Verification:** `grep -E "^script_location = alembic$" alembic.ini` → matches. `alembic history` resolves the versions directory correctly.
- **Committed in:** `92a3d4f` (Task 2 commit)

**4. [Rule 1 — Bug] Documented `pyproject.toml` array order discrepancy (no fix needed)**
- **Found during:** Task 1 (alembic dependency add)
- **Issue:** Plan acceptance said "The `dependencies = [` array order remains alphabetical (aiofiles, alembic, apscheduler, ...)" — but the array was NEVER alphabetical pre-edit (line 30 starts with `colorlog`). The plan also required "exactly one added line; no other modifications".
- **Fix:** Honored the harder constraint (exactly-one-line + preserve trailing comma). Inserted `"alembic>=1.13.0",` immediately after `"aiofiles>=25.1.0",` — alphabetically correct relative to its neighbors `aiofiles` and `apscheduler`, but the rest of the array remains in its existing non-alphabetical order. No reorder of pre-existing entries (out-of-scope per plan and per "no other modifications" rule).
- **Files modified:** `pyproject.toml` (one line added)
- **Verification:** `git diff pyproject.toml` shows exactly one addition; `grep -c "alembic>=1.13.0" pyproject.toml` → 1.
- **Committed in:** `6611353` (Task 1 commit)

---

**Total deviations:** 4 auto-fixed (3 blocking grep-gate adjustments, 1 plan-internal contradiction documentation).
**Impact on plan:** All deviations were resolutions of plan-internal contradictions (verbatim text vs grep counts, plan claim vs actual array state). Zero scope creep. Functional behavior matches the plan's stated intent in every case.

## Issues Encountered

- **Pydantic Settings env-var routing** — During greenfield smoke testing, `DATABASE__DB_URL=...` did not override `Config.DB_URL` (the nested-delimiter convention applies to the top `Settings` class, not the nested `DatabaseSettings(BaseSettings)` subclass which independently reads OS env). Plain `DB_URL=...` does override (matches the `default=...` field name). Used `DB_URL` directly for smoke tests; no app-code change needed — Config behavior is correct, just operator-facing. Worth documenting in Phase 17 ops runbook so operators know to set `DB_URL` (not `DATABASE__DB_URL`) when invoking `alembic` against alternate DB paths.

## User Setup Required

None — no external services. Subsequent operator action will live in Phase 17 runbook (`alembic stamp 0001_baseline` against production records.db before first `alembic upgrade head`).

## Next Phase Readiness

- Plan 02 (PRAGMA foreign_keys listener) can build on top — alembic env now exists for verifier integration tests
- Plan 03 (0002_auth_schema) chains directly: `down_revision = "0001_baseline"`; tasks pre-exists when batch_alter_table runs to add user_id FK
- Plan 04 (drop create_all from main.py) safe to land once 0002 is committed and verified greenfield + brownfield
- No blockers. records.db is untouched (smoke tests used copies, all cleaned up).

## Self-Check: PASSED

All claimed artifacts verified on disk:
- `alembic.ini` ✓
- `alembic/env.py` ✓
- `alembic/script.py.mako` ✓
- `alembic/versions/0001_baseline.py` ✓
- `alembic/README` ✓
- `.planning/phases/10-alembic-baseline-auth-schema/10-01-SUMMARY.md` ✓
- `pyproject.toml` contains `alembic>=1.13.0` ✓

All claimed commits resolve in git log:
- `6611353` (Task 1 chore) ✓
- `92a3d4f` (Task 2 feat) ✓
- `c0055d3` (Task 3 feat) ✓

---
*Phase: 10-alembic-baseline-auth-schema*
*Completed: 2026-04-29*
