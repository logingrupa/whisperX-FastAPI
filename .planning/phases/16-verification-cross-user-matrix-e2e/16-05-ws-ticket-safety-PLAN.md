---
phase: 16
plan: 05
type: execute
wave: 1
depends_on: [16-01]
files_modified:
  - tests/integration/test_ws_ticket_safety.py
autonomous: true
requirements: [VERIFY-07]
tags: [verification, websocket, ticket, single-use, ttl, cross-user]
must_haves:
  truths:
    - "Reused WS ticket → close 1008 on second connect"
    - "Expired WS ticket (>60s, datetime.now monkeypatched forward) → close 1008"
    - "Cross-user WS ticket (consumed_user_id != task.user_id post-issue drift) → close 1008"
  artifacts:
    - path: "tests/integration/test_ws_ticket_safety.py"
      provides: "VERIFY-07 — 3 cases (reuse, expired, cross-user) — gold copy superseding scattered checks"
      min_lines: 180
      contains: "WS_POLICY_VIOLATION"
  key_links:
    - from: "test_ws_ticket_safety.py"
      to: "tests/integration/_phase16_helpers.WS_POLICY_VIOLATION"
      via: "import constant"
      pattern: "WS_POLICY_VIOLATION"
    - from: "test_ws_reject_expired_ticket"
      to: "app.services.ws_ticket_service.datetime"
      via: "monkeypatch with _FrozenDatetime — Pitfall 4"
      pattern: "monkeypatch.setattr.*ws_ticket_service.datetime"
---

<objective>
Implement VERIFY-07 WS ticket lifecycle safety. Caveman: 3 cases — reuse, expired, cross-user drift. All close 1008.

Purpose: prove WsTicketService atomic single-use + 60s TTL + handler-side defence-in-depth (consumed_user_id != task.user_id check) all enforce.
Output: tests/integration/test_ws_ticket_safety.py (~200 lines).
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

@tests/integration/test_ws_ticket_flow.py
@tests/integration/_phase16_helpers.py
@app/services/ws_ticket_service.py
@app/api/websocket_api.py
@app/api/ws_ticket_routes.py

<interfaces>
<!-- From _phase16_helpers -->
WS_POLICY_VIOLATION: int = 1008
def _register(client, email, password=...) -> int
def _insert_task(session_factory, *, user_id, file_name=...) -> str

<!-- From existing test_ws_ticket_flow.py — patterns to copy -->
# tmp_db_url + session_factory fixtures
# ws_app fixture mounting auth + ws_ticket + websocket routers + DualAuthMiddleware (NOT CSRF — WS doesn't trigger it)
# _close_code_from_disconnect(exc: WebSocketDisconnect) -> int
# _FrozenDatetime monkeypatch on app.services.ws_ticket_service.datetime
```

</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client (forged/reused/expired ticket) → WsTicketService.consume | atomic single-use + TTL enforcement |
| client (valid ticket, wrong user) → websocket_api handler | defence-in-depth: consumed_user_id != task.user_id → 1008 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-16-02 | Tampering | TTL bypass via wall-clock | mitigate | _FrozenDatetime monkeypatch on app.services.ws_ticket_service.datetime — sub-second deterministic |
| T-16-08 | Tampering | monkeypatch leakage | mitigate | monkeypatch.setattr is function-scoped; auto-reverts after test |
| T-16-04 | Spoofing | cross-user via post-issue user_id drift | mitigate | handler re-checks ticket.user_id == task.user_id (Phase 13-07 STATE.md) |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: ws_app fixture + helpers (copy patterns from test_ws_ticket_flow.py)</name>
  <files>tests/integration/test_ws_ticket_safety.py</files>
  <read_first>
    - tests/integration/test_ws_ticket_flow.py (full file — primary template)
    - tests/integration/_phase16_helpers.py
    - app/services/ws_ticket_service.py — confirm `datetime.now(timezone.utc)` is the expiry-clock source (Pitfall 4 + RESEARCH §Pattern 6)
    - app/api/websocket_api.py — confirm consumed_user_id != task.user_id defence-in-depth check
    - app/api/ws_ticket_routes.py — confirm POST /api/ws/ticket request body shape `{"task_id": "..."}`
  </read_first>
  <action>
Create file with module docstring: "VERIFY-07 WS ticket lifecycle safety — 3 cases: reuse, expired (mocked clock), cross-user drift. All close 1008."

Imports (closely mirror test_ws_ticket_flow.py:21-49):
```python
from __future__ import annotations
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.api import dependencies
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.api.websocket_api import websocket_router
from app.api.ws_ticket_routes import ws_ticket_router
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import (
    WS_POLICY_VIOLATION,
    _insert_task,
    _register,
)
```

Fixtures — copy verbatim shape from test_ws_ticket_flow.py:60-113:
- tmp_db_url (file-based SQLite, Base.metadata.create_all)
- session_factory
- ws_app — Container override + 3 exception handlers + auth_router + ws_ticket_router + websocket_router + DualAuthMiddleware
  - NOTE: NO CsrfMiddleware here. WS handshake doesn't trigger HTTP CSRF; ticket flow IS the WS auth. Pitfall 4: "TestClient WS does NOT run middleware" — DualAuth in the stack still doesn't apply on WS scope, but ticket consume queries dependencies._container.

Helpers (copy verbatim from test_ws_ticket_flow.py):
- `_close_code_from_disconnect(exc: WebSocketDisconnect) -> int` — returns int(exc.code)

Helper `_issue_ticket(client, task_uuid) -> str`:
- response = client.post("/api/ws/ticket", json={"task_id": task_uuid}, headers={"X-CSRF-Token": client.cookies.get("csrf_token") or ""})
- assert response.status_code == 201, response.text
- return response.json()["ticket"]
(Note: ticket-issue endpoint is HTTP POST → CSRF check fires only if CsrfMiddleware mounted. Since this fixture omits CsrfMiddleware, the X-CSRF-Token header is harmless extra noise but doesn't break.)

Actually — re-read app/api/ws_ticket_routes.py to confirm whether it requires CSRF in this fixture's middleware stack. If CsrfMiddleware is omitted from ws_app, the route succeeds without X-CSRF-Token. Keep the call simple: `client.post("/api/ws/ticket", json={"task_id": task_uuid})` and skip the CSRF header — matches test_ws_ticket_flow.py line 168-188 exact behavior.

Document the fixture choice in the module docstring: "ws_app omits CsrfMiddleware (WS handshake doesn't trigger HTTP CSRF; ticket flow is the WS auth). Mirrors test_ws_ticket_flow.py pattern."
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_ws_ticket_safety.py --collect-only -q 2>&1 | head -20</automated>
  </verify>
  <done>
    - File created; pytest collects fixtures
    - ws_app mounts auth + ws_ticket + websocket routers + DualAuthMiddleware
    - _issue_ticket helper returns ticket string
    - WS_POLICY_VIOLATION imported from helpers
  </done>
  <acceptance_criteria>
    - `grep -c "include_router(websocket_router\\|include_router(ws_ticket_router\\|include_router(auth_router" tests/integration/test_ws_ticket_safety.py` >= 3
    - `grep -c "WS_POLICY_VIOLATION" tests/integration/test_ws_ticket_safety.py` >= 1
    - `grep -c "from tests.integration._phase16_helpers import" tests/integration/test_ws_ticket_safety.py` == 1
    - `grep -c "limiter.reset()" tests/integration/test_ws_ticket_safety.py` >= 2
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: 3 WS attack cases — reuse, expired (mocked clock), cross-user drift</name>
  <files>tests/integration/test_ws_ticket_safety.py</files>
  <read_first>
    - tests/integration/test_ws_ticket_safety.py (current state from Task 1)
    - tests/integration/test_ws_ticket_flow.py lines 250-340 (reuse + expired patterns to copy)
    - .planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md §test_ws_ticket_safety.py code samples
    - app/api/websocket_api.py lines 90-110 — confirm consumed_user_id != task.user_id check
  </read_first>
  <action>
Append 3 test functions:

```python
@pytest.mark.integration
def test_reused_ticket_close_1008(ws_app, session_factory) -> None:
    """Same ticket consumed twice — second connect closes 1008 (atomic single-use)."""
    app, _ = ws_app
    client = TestClient(app)
    user_id = _register(client, "ws-reuse@phase16.example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)
    ticket = _issue_ticket(client, task_uuid)

    # First consume succeeds
    with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
    # Ticket now consumed; second consume must reject
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}"):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION


@pytest.mark.integration
def test_expired_ticket_close_1008(
    ws_app, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ticket TTL exceeded (datetime.now monkeypatched forward 120s) → 1008."""
    app, _ = ws_app
    client = TestClient(app)
    user_id = _register(client, "ws-expired@phase16.example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)
    ticket = _issue_ticket(client, task_uuid)

    real_now = datetime.now(timezone.utc)
    fake_now = real_now + timedelta(seconds=120)  # 60s TTL exceeded

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    # Pitfall 4 + RESEARCH §Pattern 6: monkeypatch the SERVICE module's datetime,
    # not the global datetime. Function-scoped — auto-reverts after test.
    monkeypatch.setattr("app.services.ws_ticket_service.datetime", _FrozenDatetime)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}"):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION


@pytest.mark.integration
def test_cross_user_ticket_close_1008(ws_app, session_factory) -> None:
    """Ticket issued for User A's task; task ownership drifts before connect → handler 1008.

    Defence-in-depth: WS handler re-checks consumed_user_id == task.user_id even
    though ticket.user_id was correct at issue time. Phase 13-07 STATE.md locked
    this guard against future user_id drift bugs.
    """
    app, _ = ws_app
    client = TestClient(app)
    user_id_a = _register(client, "ws-crossuser-a@phase16.example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id_a)
    ticket = _issue_ticket(client, task_uuid)

    # Drift simulation: rewrite tasks.user_id to a non-existent id (9999) post-issue.
    with session_factory() as session:
        session.execute(
            text("UPDATE tasks SET user_id = :new WHERE uuid = :uuid"),
            {"new": 9999, "uuid": task_uuid},
        )
        session.commit()

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}"):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION
```

DRT: _issue_ticket helper used 3 times.
SRP: each test asserts ONE attack scenario.
Tiger-style: assertion message includes _close_code_from_disconnect's int (verifiable).
Names: ticket, task_uuid, fake_now, real_now, _FrozenDatetime — all self-explanatory.
No nested-if (only `with` blocks and pytest.raises context managers).
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_ws_ticket_safety.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>
    - 3 cases collected
    - All 3 close 1008
    - Reuse case: ping/pong on first connect, 1008 on second
    - Expired case: monkeypatch forward 120s, 1008
    - Cross-user case: drift task.user_id, 1008
  </done>
  <acceptance_criteria>
    - `uv run pytest tests/integration/test_ws_ticket_safety.py -q --co 2>&1 | grep -c "::test_"` == 3
    - `uv run pytest tests/integration/test_ws_ticket_safety.py -x -q` exit code 0
    - `grep -c "WS_POLICY_VIOLATION" tests/integration/test_ws_ticket_safety.py` >= 3
    - `grep -c "monkeypatch.setattr.*ws_ticket_service.datetime" tests/integration/test_ws_ticket_safety.py` >= 1 (Pitfall 4)
    - `grep -c "UPDATE tasks SET user_id" tests/integration/test_ws_ticket_safety.py` >= 1 (drift simulation)
    - Nested-if invariant: `grep -cE "        if .*:$" tests/integration/test_ws_ticket_safety.py` == 0
  </acceptance_criteria>
</task>

</tasks>

<verification>
- `uv run pytest tests/integration/test_ws_ticket_safety.py -v` → 3 green
- VERIFY-07 closed
- All 3 attack vectors close 1008 deterministically
</verification>

<success_criteria>
- 3 cases pass
- _FrozenDatetime monkeypatch correctly targets `app.services.ws_ticket_service.datetime` (NOT global datetime)
- Drift via direct UPDATE on tasks.user_id (not ORM round-trip) keeps test fast + DB-shape-stable
- Tiger-style: assert exact close code 1008
- No nested-if
- limiter.reset() in setup AND teardown
</success_criteria>

<output>
After completion, create `.planning/phases/16-verification-cross-user-matrix-e2e/16-05-SUMMARY.md`
</output>
