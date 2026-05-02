"""tests/integration/test_no_session_leak.py — Phase 19 CI gate (T-19-14).

50 sequential authed GET /api/account/me requests via the production
FastAPI TestClient. Each request MUST complete in < 100ms; p95 MUST be
< 100ms.

Pre-fix (commits 0f7bb09 / 61c9d61 era): iter ~16 hangs 30s on QueuePool
checkout — default pool_size=5 + max_overflow=10 = 15 — because the
DualAuthMiddleware + direct `_container.X()` callsites leaked a Session
per HTTP request. Post-fix (Plan 19 structural refactor): get_db owns
the ONE Session per request and closes it in the finally; every iter
< 100ms by a wide margin.

Companion: scripts/verify_session_leak_fix.py runs the same loop at the
provider level (kept per Phase 19 D6 for one full release cycle).

Tiger-style:
- Boundary asserts BEFORE loop (cookie present) and AFTER loop (p95).
- Flat early-return inside loop (assert-fast on status + elapsed).
- Self-explanatory names: _PER_REQUEST_BUDGET_MS, durations_ms.
- Per-test tmp_path engine + dependency override → full isolation.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db
from app.core.rate_limiter import limiter
from app.infrastructure.database.models import Base
from app.main import app

_ITERATIONS = 50
_PER_REQUEST_BUDGET_MS = 100.0


@pytest.fixture
def client_with_db(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Production FastAPI app bound to a tmp SQLite via dependency override.

    Mirrors Plan 19-10 migration target: app.dependency_overrides[get_db]
    is the SOLE DB-binding seam. limiter.reset() bookends the fixture so
    the slowapi 3/hr cap on /auth/register does not bleed across tests
    (singleton state hazard).
    """
    limiter.reset()

    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(
        autoflush=False, autocommit=False, bind=engine,
    )

    def _override_get_db() -> Generator:
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        limiter.reset()


def _register_user(client: TestClient, email: str = "leak-test@example.com") -> None:
    """POST /auth/register and assert session cookie landed."""
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "TestPassword!23"},
    )
    assert response.status_code == 201, f"register failed: {response.text}"
    assert client.cookies.get("session") is not None, (
        "no session cookie after register"
    )


@pytest.mark.integration
class TestNoSessionLeak:
    """50 sequential authed GET /api/account/me MUST each return < 100ms.

    Without get_db's yield/finally close (or with the dropped middleware
    direct-container leak), iter ~16 would hang 30s on QueuePool timeout.
    """

    def test_fifty_sequential_authed_requests_under_budget(
        self, client_with_db: TestClient,
    ) -> None:
        # Boundary precondition: cookies acquired before loop.
        _register_user(client_with_db)

        durations_ms: list[float] = []
        for i in range(_ITERATIONS):
            t0 = time.perf_counter()
            response = client_with_db.get("/api/account/me")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert response.status_code == 200, (
                f"iter {i}: expected 200, got {response.status_code} "
                f"(body={response.text[:200]})"
            )
            assert elapsed_ms < _PER_REQUEST_BUDGET_MS, (
                f"iter {i}: {elapsed_ms:.1f}ms exceeded "
                f"{_PER_REQUEST_BUDGET_MS}ms budget "
                f"(suggests pool exhaustion at iter {i})"
            )
            durations_ms.append(elapsed_ms)

        # Boundary postcondition: tail latency healthy.
        durations_ms.sort()
        p95 = durations_ms[int(_ITERATIONS * 0.95)]
        assert p95 < _PER_REQUEST_BUDGET_MS, (
            f"p95={p95:.1f}ms exceeded {_PER_REQUEST_BUDGET_MS}ms "
            f"(min={durations_ms[0]:.1f}, max={durations_ms[-1]:.1f}, "
            f"median={durations_ms[_ITERATIONS // 2]:.1f})"
        )
