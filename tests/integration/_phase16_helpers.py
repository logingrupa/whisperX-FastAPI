"""DRT helpers for Phase 16 verification tests.

Imported by:
    tests/integration/test_security_matrix.py    (VERIFY-01)
    tests/integration/test_jwt_attacks.py        (VERIFY-02..04)
    tests/integration/test_csrf_enforcement.py   (VERIFY-06)
    tests/integration/test_ws_ticket_safety.py   (VERIFY-07)
    tests/integration/test_migration_smoke.py    (VERIFY-08)

Single source for endpoint catalog, user seeding, JWT forging, CSRF cookie
capture, and alembic subprocess invocation. NO test logic, NO fixtures, NO
test-framework decorators here — just shared building blocks so plans
16-02..06 stay file-disjoint and parallel-safe.

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
import uuid
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
    given client's jar (auth_routes.py sets both on 201). NOTE this helper
    deliberately does NOT plumb the X-CSRF-Token header — Phase 16 CSRF
    tests rely on the header being absent by default so the missing-header
    leg surfaces. Tests that want pre-plumbed CSRF should set
    ``client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")``
    after calling this helper (test_security_matrix follows that pattern).
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

    task_uuid = str(uuid.uuid4())
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


# ---------------------------------------------------------------------------
# JWT forging — kwargs-only; three deterministic branches:
#   alg=none → bypass PyJWT (which refuses alg=none on encode)
#   HS256 + tamper → real signature with last byte flipped
#   HS256 + expired → real signature, ``iat``/``exp`` shifted to the past
# Every branch is a flat early-return guard. No nested-if.
# ---------------------------------------------------------------------------


def _b64url(raw: dict | bytes) -> str:
    """Base64url-encode (no padding) JSON-serialised dicts or raw bytes.

    JWT segments are base64url with padding stripped per RFC 7515 §2.
    """
    payload_bytes = (
        raw if isinstance(raw, bytes)
        else json.dumps(raw, separators=(",", ":")).encode()
    )
    return base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")


def _forge_jwt(
    *,
    alg: str,
    user_id: int,
    token_version: int = 0,
    secret: str | None = None,
    expired: bool = False,
    tamper: bool = False,
) -> str:
    """Forge a JWT for security tests.

    Branches (mutually-exclusive, flat early-returns):
        alg == JWT_ALG_NONE   → header={"alg":"none"}, empty signature segment.
        alg == JWT_HS256      → real HS256 sign with ``secret``;
                                ``expired=True`` shifts iat/exp into the past;
                                ``tamper=True`` flips the last char of the sig.

    Args:
        alg:           ``JWT_ALG_NONE`` or ``JWT_HS256``.
        user_id:       Subject claim (serialized as str per RFC 7519 §4.1.2).
        token_version: Goes into the ``ver`` claim.
        secret:        REQUIRED for HS256 branches; ignored for alg=none.
        expired:       HS256 only — shift iat to now-86400, exp to now-3600.
        tamper:        HS256 only — flip last char of the signature.

    Returns:
        Compact JWT string ``header.payload.signature``.
    """
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now - 86400 if expired else now,
        "exp": now - 3600 if expired else now + 86400,
        "ver": token_version,
        "method": "session",
    }
    if alg == JWT_ALG_NONE:
        header = {"alg": "none", "typ": "JWT"}
        return f"{_b64url(header)}.{_b64url(payload)}."
    assert secret is not None, "HS256 forge requires secret"
    token = jwt.encode(payload, secret, algorithm=JWT_HS256)
    if not tamper:
        return token
    head, body, sig = token.split(".")
    flipped_char = "A" if sig[-1] != "A" else "B"
    return f"{head}.{body}.{sig[:-1]}{flipped_char}"


# ---------------------------------------------------------------------------
# CSRF cookie capture — single register + jar-read.
# ---------------------------------------------------------------------------


def _issue_csrf_pair(client: TestClient, email: str) -> tuple[str, str]:
    """Register ``email`` on ``client`` and return ``(session, csrf_token)``.

    auth_routes.register stamps both cookies on the 201 response, which the
    httpx jar inside TestClient captures automatically. Tiger-style: assert
    both cookies are present so missing-cookie regressions fail loud.
    """
    _register(client, email)
    session = client.cookies.get("session")
    csrf = client.cookies.get("csrf_token")
    assert session is not None, "session cookie missing after register"
    assert csrf is not None, "csrf_token cookie missing after register"
    return (session, csrf)


# ---------------------------------------------------------------------------
# Alembic subprocess wrapper — venv-portable per Plan 10-04 lesson.
# Mirrors test_alembic_migration.py:34-53 verbatim.
# ---------------------------------------------------------------------------


def _run_alembic(
    args: list[str], db_url: str
) -> subprocess.CompletedProcess[str]:
    """Invoke the alembic CLI with ``DB_URL`` pointed at ``db_url``.

    Args:
        args:    Alembic subcommand args (e.g. ``["upgrade", "head"]``).
        db_url:  SQLAlchemy URL string for the target DB.

    Returns:
        The completed process; raises ``CalledProcessError`` on non-zero exit.
    """
    env = os.environ.copy()
    env["DB_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
