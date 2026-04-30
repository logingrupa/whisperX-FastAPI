"""DRT helpers for Phase 16 verification tests.

Imported by:
    tests/integration/test_security_matrix.py    (VERIFY-01)
    tests/integration/test_jwt_attacks.py        (VERIFY-02..04)
    tests/integration/test_csrf_enforcement.py   (VERIFY-06)
    tests/integration/test_ws_ticket_safety.py   (VERIFY-07)
    tests/integration/test_migration_smoke.py    (VERIFY-08)

Single source for endpoint catalog, user seeding, JWT forging, CSRF cookie
capture, and alembic subprocess invocation. NO test logic, NO fixtures, NO
``@pytest.mark.*`` here — just shared building blocks so plans 16-02..06 stay
file-disjoint and parallel-safe.

Code-quality invariants (verifier-checked):
    DRY  — single shared module; ENDPOINT_CATALOG hardcoded once.
    SRP  — each helper has exactly one job.
    Tiger-style — assertions at every boundary (status codes, cookies).
    No nested-if — only flat early-return guards.
    Self-explanatory naming — kwargs-only on multi-arg helpers.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WS_POLICY_VIOLATION = 1008
"""WebSocket close code for policy-violation rejections (RFC 6455 §7.4.1)."""

JWT_HS256 = "HS256"
"""Algorithm name accepted by ``app.core.jwt_codec`` (single source)."""

JWT_ALG_NONE = "none"
"""RFC 7519 §6.1 alg=none — must be lowercase per spec."""

REPO_ROOT = Path(__file__).resolve().parents[2]
"""Project root: parents[2] of ``tests/integration/_phase16_helpers.py``."""


# ---------------------------------------------------------------------------
# Endpoint catalog — VERIFY-01 cross-user matrix + VERIFY-06 CSRF surface.
# Tuple shape: (method, path_template, expected_foreign_status, requires_csrf)
# Path placeholders: {task_uuid}, {key_id}
#
# Verified against actual @router decorators (grep app/api/, this session):
#   - task_router (no prefix):              GET /task/all,
#                                           GET /task/{identifier},
#                                           DELETE /task/{identifier}/delete,
#                                           GET /tasks/{identifier}/progress
#   - ws_ticket_router prefix=/api/ws:      POST /ticket
#   - key_router prefix=/api/keys:          DELETE /{key_id}
#   - account_router prefix=/api/account:   DELETE /data, GET /me, DELETE ""
#
# expected_foreign_status semantics:
#   - 200 — endpoint scopes to caller (own data) so cross-user produces no leak
#           (e.g. GET /task/all returns the foreign user's empty list, not A's;
#            GET /api/account/me returns B's own row).
#   - 204 — write succeeds against caller's own (empty) namespace
#           (DELETE /api/account/data on a brand-new B → 204 with no rows).
#   - 404 — opaque anti-enumeration (T-13-24): unknown-id and foreign-id
#           produce the SAME 404; cross-user mutations on A's resources →
#           404 not 403 to prevent existence disclosure.
# ---------------------------------------------------------------------------

ENDPOINT_CATALOG: list[tuple[str, str, int, bool]] = [
    ("GET",    "/task/all",                    200, False),
    ("GET",    "/task/{task_uuid}",            404, False),
    ("DELETE", "/task/{task_uuid}/delete",     404, True),
    ("GET",    "/tasks/{task_uuid}/progress",  404, False),
    ("POST",   "/api/ws/ticket",               404, True),
    ("DELETE", "/api/keys/{key_id}",           404, True),
    ("DELETE", "/api/account/data",            204, True),
    ("GET",    "/api/account/me",              200, False),
]
assert len(ENDPOINT_CATALOG) == 8, "ENDPOINT_CATALOG drift"


# ---------------------------------------------------------------------------
# User seeding — flat helpers, kwargs-only on multi-arg signatures.
# ---------------------------------------------------------------------------


def _register(
    client: TestClient, email: str, password: str = "supersecret123"
) -> int:
    """Register a user via ``POST /auth/register``; return ``user_id``.

    Side effect: ``session`` + ``csrf_token`` cookies are seated on the
    given client's jar (auth_routes.py sets both on 201).
    """
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["user_id"])


def _seed_two_users(
    client_a: TestClient, client_b: TestClient
) -> tuple[int, int]:
    """Register User A on ``client_a`` + User B on ``client_b``.

    Each TestClient must have its own cookie jar so the two users stay
    independent (no jar collision masks isolation bugs — see
    test_account_routes.py:319-321 pattern).
    """
    user_a_id = _register(client_a, "user-a@phase16.example.com")
    user_b_id = _register(client_b, "user-b@phase16.example.com")
    return (user_a_id, user_b_id)


def _insert_task(
    session_factory, *, user_id: int, file_name: str = "audio.mp3"
) -> str:
    """Insert one ``tasks`` row owned by ``user_id``; return its UUID.

    Lazy ORM import keeps this module loadable without a bound DB engine.
    """
    from app.infrastructure.database.models import Task as ORMTask

    task_uuid = (
        f"uuid-u{user_id}-{datetime.now(timezone.utc).timestamp()}"
    )
    with session_factory() as session:
        session.add(
            ORMTask(
                uuid=task_uuid,
                status="pending",
                file_name=file_name,
                task_type="speech-to-text",
                user_id=user_id,
            )
        )
        session.commit()
    return task_uuid
