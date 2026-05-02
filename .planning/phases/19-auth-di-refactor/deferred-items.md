# Phase 19 — Deferred Items

Items discovered during plan execution that are out-of-scope and tracked here per
the GSD scope-boundary rule.

## Pre-existing test failures observed during T-19-04 full suite

Run: `pytest tests/` on commit b6306ef (Plan 04 RED) and post-Plan-04 GREEN —
SAME 27 failures in both, untouched by Plan 04 work.

| File | Failure family | Last touched | Root cause (suspected) |
|------|----------------|--------------|------------------------|
| `tests/e2e/test_audio_processing_endpoints.py` (2) | 401 / DI | Phase 11 | Legacy bearer middleware; needs AUTH_V2_ENABLED=false + API_BEARER_TOKEN; container DI mismatch |
| `tests/e2e/test_callback_endpoints.py` (5) | 401 | Phase 11 | Same as above |
| `tests/e2e/test_task_endpoints.py` (4) | 401 | Phase 11 | Same as above |
| `tests/integration/test_task_lifecycle.py` (7) | sqlite3 FK constraint | Phase 11 | `_insert_task` seeds user_id=1 without registering a User row; tasks.user_id FK rejects |
| `tests/unit/core/test_config.py` (1) | AuthSettings prod-guard | Phase 11 | Validator refuses default secrets when V2_ENABLED=true; test predates the validator |
| `tests/unit/services/test_audio_processing_service.py` (3) | mock chain | Phase 11 | Pre-existing mock setup issue |
| `tests/integration/test_phase13_e2e_smoke.py` (1) | env-var test infra | Phase 13 | `_v2_disabled` collection error |

All 27 failures pre-date Plan 04. Phase 19 Plan 19 (final cleanup) or a
dedicated test-housekeeping plan should triage and either fix or quarantine
them with `@pytest.mark.skip` and rationale.

Plan 04 success criterion "no regression vs Plan 03 baseline" satisfied —
same failure set both before and after.

## Pre-existing failure observed during T-19-12

`tests/integration/test_free_tier_gate.py::test_free_user_6th_transcribe_returns_429_with_retry_after`
fails with `RuntimeError: Container not initialized. Call set_container() first.`
at `app/api/dependencies.py:366` (inside `_get_user_scoped_task_repository`).
Reproduces identically on HEAD (commit `c4dfbfd`) BEFORE Plan 19-12 changes
(verified via `git stash` round-trip). Root cause is the test bypassing
`app/main.py`'s `dependencies.set_container(container)` boot path while
exercising a v1.1 audio route that still resolves through `_container`.
Resolution will land naturally in Plan 19-13 when `_container` is deleted
and the v1.1 routes migrate to `Depends(get_db)` chain.
