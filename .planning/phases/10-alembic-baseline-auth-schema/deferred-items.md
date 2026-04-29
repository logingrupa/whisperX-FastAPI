# Deferred Items — Phase 10

## Pre-existing test environment gaps (out of scope, not introduced by Phase 10)

- **factory_boy not installed in .venv** — `tests/integration/test_task_lifecycle.py` imports `factory` (via `tests.factories.task_factory`). Module missing in venv. Pre-existing condition (verified by stashing Phase 10-04 changes and re-running collection). Caused by `pip install` not running for dev/test deps after venv recreation. Discovered during Plan 10-04 Task 3 verification when running `pytest tests/integration/ -m integration`.
  - **Action needed:** Add `factory-boy` to dev/test dependency group in `pyproject.toml` and `pip install` in venv before Phase 16 verifier matrix.
  - **Impact on Phase 10:** None. `test_alembic_migration.py` (the new tests) all pass. Existing `test_task_lifecycle.py` was already non-collectable before this plan.

- **mypy / ruff not installed in .venv** — Documented in 10-01 SUMMARY and 10-02 SUMMARY. Same root cause (missing dev deps). Linting / type-checking deferred to Phase 16.

- **pre-commit not installed in .venv** — Documented in 10-01 SUMMARY. Defer to Phase 16.

## Plan 10-04 environment fix applied (in scope)

- **pytest installed during Task 3 execution** — `pytest` was missing in venv at the start of Plan 10-04. Plan acceptance gate required `pytest tests/integration/test_alembic_migration.py -v -m integration` to exit 0. Per deviation Rule 3 (auto-fix blocking issue): installed `pytest` (9.0.3) into `.venv` to enable the verification step. This is the minimum needed to satisfy the plan's acceptance gates without scope creep into broader dev-tooling installation.
