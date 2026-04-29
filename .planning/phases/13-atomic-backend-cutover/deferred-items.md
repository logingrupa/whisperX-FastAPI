# Phase 13 — Deferred items log

Out-of-scope discoveries logged during plan execution. Each entry is a
SCOPE BOUNDARY exclusion: a failure not caused by the executing plan and
not in scope to fix.

## Discovered during 13-06 execution (2026-04-29)

- **`tests/unit/services/test_audio_processing_service.py`** — 3 failures pre-existing on
  the main branch BEFORE plan 13-06. The `update` mock-call assertions expect 1 call but
  the production path now emits 4 (queued / transcribing / complete / status). Out of scope
  for plan 13-06 (concerns audio progress emission, not WS ticket / MID-06 / MID-07).
- **`tests/unit/{domain/entities/test_task.py, infrastructure/database/mappers/test_task_mapper.py, infrastructure/database/repositories/test_sqlalchemy_task_repository.py}`** — collection
  errors due to missing `factory` package (`ModuleNotFoundError: No module named 'factory'`).
  Pre-existing — unrelated test-infrastructure dependency missing.
