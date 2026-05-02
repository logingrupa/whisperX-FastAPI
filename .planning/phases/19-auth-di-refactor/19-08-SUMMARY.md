---
phase: 19-auth-di-refactor
plan: 08
subsystem: api/websocket
tags: [websocket, session-lifecycle, di]

# Dependency graph
requires:
  - phase: 19-auth-di-refactor
    provides: "app.core.services.get_ws_ticket_service singleton (Plan 02)"
provides:
  - "WS handler uses explicit `with SessionLocal() as db:` block — context-manager owns close()"
  - "Zero `_container.X()` references in websocket_api.py"
affects: [19-12, 19-13]

key-files:
  modified:
    - "app/api/websocket_api.py — drop _container reach-ins; with SessionLocal() block + singleton import"
    - "tests/integration/test_ws_ticket_flow.py — monkey-patch SessionLocal -> session_factory"
    - "tests/integration/test_ws_ticket_safety.py — monkey-patch SessionLocal -> session_factory"

key-decisions:
  - "WS scope has no FastAPI Depends, so test fixtures monkey-patch module-level SessionLocal. The session_factory is a sessionmaker — same shape as production SessionLocal — so substitution works"
  - "Five flat guards preserved; MID-07 defence-in-depth kept verbatim"
  - "Dropped the `if dependencies._container is None: ...` defensive guard — singleton always available"

requirements-completed: [REFACTOR-01, REFACTOR-02]

# Metrics
duration: 8min
completed: 2026-05-02
---

# Phase 19 Plan 08: websocket-migration Summary

**WS handler in `app/api/websocket_api.py` migrated to explicit `with SessionLocal() as db:` block (context-manager owns close) + `app.core.services.get_ws_ticket_service` singleton. Zero `_container` references remain.**

## Performance

- Duration: ~8 min
- Files modified: 3
- Commit: `7cf615e` — refactor(19-08): WS handler uses SessionLocal context-manager + ws_ticket_service singleton

## Verification

- `grep -c "_container" app/api/websocket_api.py` == 0 ✓
- `grep -c "with SessionLocal() as db:" app/api/websocket_api.py` == 2 (1 docstring + 1 code) ✓
- `grep -c "session.close()" app/api/websocket_api.py` == 0 ✓
- `grep -c "from app.core.services import get_ws_ticket_service" app/api/websocket_api.py` == 1 ✓
- 5 flat guards preserved (no nested-if)
- MID-07 defence-in-depth check (`consumed_user_id != task.user_id`) kept
- 14/14 WS ticket tests GREEN

## Notes

- Test fixtures use monkeypatch on `app.api.websocket_api.SessionLocal` (assignment, not `monkeypatch.setattr`) — sufficient because `ws_app` fixture cleans up via `original_session_local` save+restore.

## Status

PLAN COMPLETE
