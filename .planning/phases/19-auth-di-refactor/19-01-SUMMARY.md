---
phase: 19-auth-di-refactor
plan: 01
subsystem: testing
tags: [pytest, baseline, regression-gate, factory-boy, deviation-log]

# Dependency graph
requires:
  - phase: 17-docs-migration-runbook-operator-guide
    provides: post-Phase-17 codebase + 500-test pytest suite
provides:
  - tests/baseline_phase19.txt (500 sorted nodeids — end-of-phase regression diff anchor)
  - DEVIATIONS.md Phase 13 atomic-cutover lock waiver entry committed (was already tracked from plan-phase commit 2e89924)
affects: [19-17 final verification gate 5+6, all 19-NN intermediate tasks (each must keep collection >= 500 nodeids)]

# Tech tracking
tech-stack:
  added: [factory-boy 3.3.3 (test dep — was in pyproject but not in .venv)]
  patterns:
    - "pytest --collect-only -qq emits path::Class::method nodeids on pytest 9.x (not -q)"
    - "Filter raw collect output via regex `^[A-Za-z0-9_./\\\\-]+\\.py::[A-Za-z0-9_:\\\\-]+(\\[.+\\])?$` to strip warnings/headers"

key-files:
  created:
    - tests/baseline_phase19.txt
  modified: []

key-decisions:
  - "Use pytest -qq (not -q) on pytest 9.0.3 — only -qq emits flat path::Class::method nodeids; -q emits hierarchical tree of <Module>/<Function> wrappers"
  - "Install missing factory-boy at execution time rather than capture errored baseline — 4 test modules fail to collect without it; baseline must reflect collectable suite for diff to be meaningful"
  - "Single-commit (chore commit covers baseline only) — DEVIATIONS.md was already committed in plan-phase commit 2e89924; physical 'both files in same commit' gate is inapplicable, logical pair is intact"

patterns-established:
  - "Pattern: Phase-start regression baseline via pytest --collect-only -qq | regex-filter | sort > tests/baseline_phaseNN.txt — reusable for any future structural-refactor phase"

requirements-completed: [REFACTOR-06]

# Metrics
duration: 8min
completed: 2026-05-02
---

# Phase 19 Plan 01: Baseline Snapshot + DEVIATIONS Waiver Summary

**500-node pytest collection inventory pinned to tests/baseline_phase19.txt as the end-of-phase regression diff anchor; Phase 13 atomic-cutover lock waiver entry confirmed in .planning/DEVIATIONS.md.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-02T15:11:00Z (approx)
- **Completed:** 2026-05-02T15:19:00Z
- **Tasks:** 1 / 1
- **Files modified:** 1 created (tests/baseline_phase19.txt), 0 source files touched

## Accomplishments

- Generated deterministic 500-nodeid sorted baseline from `pytest --collect-only -qq` covering full `tests/` suite at phase start
- Confirmed `.planning/DEVIATIONS.md` already carries the 2026-05-02 Phase 13 atomic-cutover-lock waiver entry (committed in plan-phase commit `2e89924`)
- Restored ability to collect 4 test modules (`test_task_lifecycle`, `test_task`, `test_task_mapper`, `test_sqlalchemy_task_repository`) by installing missing `factory-boy==3.3.3` into `.venv`

## Task Commits

Each task was committed atomically:

1. **Task 1: Generate pytest baseline + commit DEVIATIONS waiver as one atomic commit** — `b83d3d8` (chore)

_DEVIATIONS.md waiver entry was committed earlier in plan-phase commit `2e89924`; this plan's commit covers the new baseline file only._

## Files Created/Modified

- `tests/baseline_phase19.txt` — 500 sorted pytest nodeids; deterministic newline-separated list. Diff target for verification gate 6 at T-19-17.

## Decisions Made

- **`-qq` over `-q`:** pytest 9.0.3 changed quiet-mode output. `-q` produces hierarchical `<Module>/<Function>` tree; only `-qq` produces flat `path::Class::method` nodeids the plan needs. Documented in commit body for future plan adjustments.
- **Install missing dep over capture-with-errors:** The point of the baseline is regression diff. Capturing 4 collection errors as "the truth" would force end-of-phase to also have 4 errors — inverted gate. Installing factory-boy (already declared in `pyproject.toml:63`) is correct fix.
- **Single commit instead of paired commit:** Plan's `<verify>` gate `git log -1 --name-only shows both files in the same commit` is unmeetable because DEVIATIONS.md was already committed in `2e89924` (plan-phase). The logical artefact pair is intact across two commits; the physical-paired form was a planner assumption that didn't survive plan-phase work order.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing factory-boy 3.3.3 into .venv**
- **Found during:** Task 1, first invocation of `pytest --collect-only`
- **Issue:** `ModuleNotFoundError: No module named 'factory'` — 4 test modules (`test_task_lifecycle.py`, `test_task.py`, `test_task_mapper.py`, `test_sqlalchemy_task_repository.py`) fail to collect; pytest exits with code 2 and "Interrupted: 4 errors during collection". Without the dep installed, the baseline would either short by 4 modules' worth of tests OR carry collection errors into the regression gate.
- **Fix:** `.venv/Scripts/python.exe -m pip install factory-boy==3.3.3` — exact version already declared in `pyproject.toml:63`; just absent from local `.venv`.
- **Files modified:** none in repo (venv-only state)
- **Verification:** Re-ran `pytest --collect-only -qq`; exit 0; "500 tests collected" reported (vs 455 collected + 4 errors before).
- **Committed in:** `b83d3d8` (Task 1 commit; deviation documented in commit body)

**2. [Rule 3 - Blocking] Switched pytest invocation from `-q` to `-qq`**
- **Found during:** Task 1, output inspection
- **Issue:** Plan said `pytest --collect-only -q` and to "keep only `path::Class::method` style lines". On pytest 9.0.3 with this codebase, `-q` produces a hierarchical `<Dir>/<Package>/<Module>/<Function>` tree — ZERO `path::Class::method` lines, so the regex filter would write an empty file and the >=500 gate would fail.
- **Fix:** Use `-qq` (double-quiet) which on pytest 9.x emits the flat nodeid form. Filter regex tightened to `^[A-Za-z0-9_./\-]+\.py::[A-Za-z0-9_:\-]+(\[.+\])?$` to capture parametrized cases too (e.g. `test_x[400-False]`).
- **Files modified:** none
- **Verification:** Output spot-checked head and tail; first line `tests/e2e/test_audio_processing_endpoints.py::test_align_service`, last line `tests/unit/test_callbacks.py::TestCallbacks::test_validate_callback_url_status_codes[502-False]`. Line count == 500 == "tests collected" reported by pytest.
- **Committed in:** `b83d3d8`

**3. [Rule 3 - Planner contract drift] DEVIATIONS.md was already committed in plan-phase**
- **Found during:** Task 1, initial `git status` review
- **Issue:** Plan instructed `git add tests/baseline_phase19.txt .planning/DEVIATIONS.md` followed by single commit, with verify gate `git log -1 --name-only shows both files in the same commit`. But `git ls-files` showed DEVIATIONS.md already tracked (in `2e89924`), so re-staging it produced no diff and `git log -1` cannot show two new files in one commit.
- **Fix:** Commit only the new file. Document the discrepancy in commit body and SUMMARY. The waiver entry is verifiable via `grep -c "Phase 13 atomic-cutover lock waived" .planning/DEVIATIONS.md == 1` (still passes).
- **Files modified:** none
- **Verification:** `grep -q "Phase 13 atomic-cutover lock waived" .planning/DEVIATIONS.md` → match; `wc -l tests/baseline_phase19.txt` → 500 (>= 500 gate passes).
- **Committed in:** `b83d3d8` (deviation documented in commit body)

---

**Total deviations:** 3 auto-fixed (3 Rule 3 — blocking)
**Impact on plan:** Zero scope creep. Baseline file is the deterministic artefact the plan asked for; DEVIATIONS.md waiver is committed (just earlier than plan assumed). End-of-phase regression diff (T-19-17 gate 6) has its anchor.

## Issues Encountered

None beyond the deviations above. Plan's intent (gate-zero artefact pinned, phase 13 lock waiver in audit trail) is fully satisfied.

## User Setup Required

None. Phase-internal change; no external service configuration.

## Next Phase Readiness

- **Ready for T-19-02:** plan/research/patterns all read; codebase state baseline. T-19-02 creates `app/core/services.py` with `@lru_cache(maxsize=1)` singletons (existing container coexists; smoke-wire one route).
- **Concerns:** None blocking. The `factory-boy` install in `.venv` is local; CI/operator runners will need `uv sync` to pick it up. The package is already declared in `pyproject.toml`, so no source-tree action needed.

## Self-Check: PASSED

- `tests/baseline_phase19.txt` exists (500 lines)
- `.planning/DEVIATIONS.md` carries waiver entry (`grep -c "Phase 13 atomic-cutover lock waived" == 1`)
- Commit `b83d3d8` is in `git log` for branch `main`
- `wc -l tests/baseline_phase19.txt` == 500 (>= 500 gate)
- No source-tree files modified outside the test inventory file

---
*Phase: 19-auth-di-refactor*
*Completed: 2026-05-02*
