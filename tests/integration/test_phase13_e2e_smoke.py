"""Phase 13 end-to-end smoke test — atomic-flip gate.

Spawns a fresh ``uvicorn`` subprocess per scenario (clean module state, fresh
engine binding, fresh ``slowapi`` bucket, fresh ``settings.lru_cache``) and
exercises every locked must-have from Phase 13:

  - register → cookie set
  - login → cookie set
  - create key (show-once plaintext)
  - use key as ``Authorization: Bearer whsk_*`` to call protected route
  - delete key (soft-delete)
  - logout (cookies cleared)
  - cross-user 404 isolation (User B GET A's key → 404 opaque)
  - rate-limit ``ANTI-01`` (4th register from same /24 → 429 + Retry-After)
  - disposable-email rejection (``ANTI-04`` 422 generic)
  - CORS preflight allowlist + credentials echo (``ANTI-06``)
  - CORS preflight from non-allowlisted origin → no ACAO
  - Stripe stubs return 501 (``BILL-05/06``); malformed signature → 400
  - ``AUTH_V2_ENABLED=false`` → /auth/register NOT registered (404 with auth)
  - ``AUTH_V2_ENABLED=true``  → /auth/register registered (422 on empty body)
  - ``CSRF`` required on cookie-auth POST (``MID-04``)
  - Bearer auth skips CSRF (bearer wins; no double-submit needed)

This is the pre-flight smoke gate for the Phase 13 + Phase 14 atomic deploy.
Cross-user matrix / JWT attack matrix / WS reuse tests live in Phase 16.
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_BOOT_TIMEOUT_SECONDS = 90
_BOOT_POLL_SECONDS = 0.5


# ---------------------------------------------------------------
# Subprocess lifecycle helpers (DRY)
# ---------------------------------------------------------------


def _free_port() -> int:
    """Return a free TCP port on 127.0.0.1 (port=0 => OS-allocated)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_env(env_overrides: dict[str, str], db_path: Path) -> dict[str, str]:
    """Return a clean env dict with Phase 13 test secrets baked in.

    Each subprocess gets fresh ``AUTH__JWT_SECRET`` + ``AUTH__CSRF_SECRET``
    (urlsafe(32)) so token forgery across runs is impossible. ``ENVIRONMENT``
    is forced to ``development`` so the production-safety guard never fires.
    Inherits PATH / SystemRoot / etc. from the parent shell so Python resolves
    the venv properly on Windows.
    """
    env = os.environ.copy()
    # Strip parent .env state that would alter test deterministically.
    for stale in ("AUTH__V2_ENABLED", "AUTH__COOKIE_SECURE", "AUTH__FRONTEND_URL"):
        env.pop(stale, None)
    env["DB_URL"] = f"sqlite:///{db_path}"
    env["AUTH__JWT_SECRET"] = secrets.token_urlsafe(32)
    env["AUTH__CSRF_SECRET"] = secrets.token_urlsafe(32)
    env["AUTH__FRONTEND_URL"] = "http://localhost:5173"
    env["AUTH__COOKIE_SECURE"] = "false"  # http test client
    env["ENVIRONMENT"] = "development"
    env.update(env_overrides)
    return env


def _start_server(
    env_overrides: dict[str, str], db_path: Path, port: int,
) -> subprocess.Popen[bytes]:
    """Run ``alembic upgrade head`` then spawn uvicorn; return live process.

    Tiger-style fail-loud: if the child does not respond on ``/health`` within
    ``_BOOT_TIMEOUT_SECONDS`` seconds we kill it, drain stderr, raise.
    """
    env = _build_env(env_overrides, db_path)
    # Migrate the tmp DB to head BEFORE booting the app (engine binds at module
    # load — we cannot rely on autogen). 0001+0002+0003 from Phase 10/12.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.time() + _BOOT_TIMEOUT_SECONDS
    while time.time() < deadline:
        time.sleep(_BOOT_POLL_SECONDS)
        # Bail early if process died at import.
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(
                f"uvicorn exited rc={proc.returncode} during boot.\n"
                f"stdout:\n{out.decode(errors='replace')}\n"
                f"stderr:\n{err.decode(errors='replace')}"
            )
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
        except httpx.RequestError:
            continue
        if response.status_code == 200:
            return proc
    proc.kill()
    out, err = proc.communicate()
    raise RuntimeError(
        f"Server did not boot within {_BOOT_TIMEOUT_SECONDS}s. "
        f"stderr:\n{err.decode(errors='replace')}"
    )


def _stop_server(proc: subprocess.Popen[bytes]) -> None:
    """Terminate child cleanly; SIGKILL after 5s grace."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------
# Fixtures (V2 ON / V2 OFF)
# ---------------------------------------------------------------


@pytest.fixture
def server_v2_on(tmp_path: Path) -> Generator[str, None, None]:
    """Boot uvicorn with ``AUTH__V2_ENABLED=true`` + tmp SQLite DB."""
    port = _free_port()
    db = tmp_path / "smoke_v2on.db"
    proc = _start_server({"AUTH__V2_ENABLED": "true"}, db, port)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        _stop_server(proc)


@pytest.fixture
def server_v2_off(tmp_path: Path) -> Generator[str, None, None]:
    """Boot uvicorn with ``AUTH__V2_ENABLED=false`` (legacy fallback path).

    Sets a real ``API_BEARER_TOKEN`` so the legacy ``BearerAuthMiddleware``
    passes the request to the FastAPI router — only then can we observe that
    Phase 13 routes return 404 (route not registered). Without the bearer
    header the middleware would short-circuit at 401 and we could not
    distinguish "auth missing" from "route absent".
    """
    port = _free_port()
    db = tmp_path / "smoke_v2off.db"
    proc = _start_server(
        {
            "AUTH__V2_ENABLED": "false",
            "API_BEARER_TOKEN": "smoke-legacy-token",
        },
        db,
        port,
    )
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        _stop_server(proc)


# ---------------------------------------------------------------
# DRY helper: register a fresh user, return cookies dict
# ---------------------------------------------------------------


def _register(
    client: httpx.Client, email: str, password: str = "supersecret123",
) -> dict[str, str]:
    """POST /auth/register; assert 201; return ``{session, csrf_token}`` dict.

    Clears the client's persistent cookie jar BEFORE issuing the request so
    that prior registrations on the same ``httpx.Client`` instance do not
    auto-attach a stale session — which would trigger CsrfMiddleware on the
    POST and reject with 403 ``CSRF token missing`` (state-mutating cookie
    auth requires the double-submit header). The returned cookie dict is the
    canonical session for the just-registered user; callers pass it
    explicitly via ``cookies=`` per request.
    """
    client.cookies.clear()
    response = client.post(
        "/auth/register", json={"email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    cookies = dict(response.cookies)
    assert "session" in cookies
    assert "csrf_token" in cookies
    # Wipe jar again so subsequent client.* calls in the test don't auto-send
    # the cookies — tests pass them explicitly via cookies= where needed.
    client.cookies.clear()
    return cookies


# ---------------------------------------------------------------
# Tests — one class per concern (SRP)
# ---------------------------------------------------------------


@pytest.mark.integration
def test_full_register_login_create_key_use_key_logout_flow(
    server_v2_on: str,
) -> None:
    """End-to-end happy path: register → create key → bearer-auth → revoke → logout."""
    with httpx.Client(base_url=server_v2_on) as client:
        # 1. Register — issues session + CSRF cookies.
        register_resp = client.post(
            "/auth/register",
            json={"email": "alice@example.com", "password": "supersecret123"},
        )
        assert register_resp.status_code == 201, register_resp.text
        cookies = dict(register_resp.cookies)
        assert "session" in cookies
        assert "csrf_token" in cookies
        csrf = cookies["csrf_token"]

        # 2. Create API key (cookie auth + CSRF double-submit).
        create_resp = client.post(
            "/api/keys",
            json={"name": "smoke-key"},
            cookies=cookies,
            headers={"X-CSRF-Token": csrf},
        )
        assert create_resp.status_code == 201, create_resp.text
        payload = create_resp.json()
        assert payload["key"].startswith("whsk_")
        assert len(payload["key"]) == 36
        api_key = payload["key"]
        key_id = payload["id"]

        # 3. List keys via cookie auth — show-once contract: no plaintext.
        list_resp = client.get("/api/keys", cookies=cookies)
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert "key" not in items[0]
        assert items[0]["status"] == "active"

        # 4. Use bearer key (no cookie) to list keys.
        bearer_resp = client.get(
            "/api/keys", headers={"Authorization": f"Bearer {api_key}"},
        )
        assert bearer_resp.status_code == 200, bearer_resp.text
        assert len(bearer_resp.json()) == 1

        # 5. Revoke key (soft-delete).
        revoke_resp = client.delete(
            f"/api/keys/{key_id}",
            cookies=cookies,
            headers={"X-CSRF-Token": csrf},
        )
        assert revoke_resp.status_code == 204

        # 6. List again — key shows as revoked (soft-delete preserves row).
        post_revoke = client.get("/api/keys", cookies=cookies)
        assert post_revoke.status_code == 200
        revoked_items = post_revoke.json()
        assert len(revoked_items) == 1
        assert revoked_items[0]["status"] == "revoked"

        # 7. Logout — Set-Cookie deletions emitted on the wire.
        logout_resp = client.post(
            "/auth/logout",
            cookies=cookies,
            headers={"X-CSRF-Token": csrf},
        )
        assert logout_resp.status_code == 204
        # FastAPI emits ``Max-Age=0`` (or expires=...; 1970) on cookie deletion
        # via Response.delete_cookie.
        set_cookie_header = logout_resp.headers.get("set-cookie", "")
        assert "Max-Age=0" in set_cookie_header or 'expires=Thu, 01 Jan 1970' in set_cookie_header


@pytest.mark.integration
def test_login_after_register_succeeds(server_v2_on: str) -> None:
    """register → logout → login round-trip — proves credentials persist."""
    with httpx.Client(base_url=server_v2_on) as client:
        cookies = _register(client, email="login@example.com")
        # Logout the user we just registered. Pass cookies+CSRF inline (httpx
        # will auto-merge into the jar, but we wipe immediately afterwards so
        # the next call is fully anonymous and not flagged by CsrfMiddleware).
        logout = client.post(
            "/auth/logout", cookies=cookies,
            headers={"X-CSRF-Token": cookies["csrf_token"]},
        )
        assert logout.status_code == 204, logout.text
        client.cookies.clear()
        # Fresh login MUST succeed and re-issue cookies (anonymous request,
        # no session in jar → DualAuth treats as public allowlist; no CSRF).
        login_resp = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "supersecret123"},
        )
        assert login_resp.status_code == 200, login_resp.text
        new_cookies = dict(login_resp.cookies)
        assert "session" in new_cookies
        assert "csrf_token" in new_cookies


@pytest.mark.integration
def test_cross_user_404_isolation(server_v2_on: str) -> None:
    """User B's DELETE on User A's key returns 404 opaque (no enumeration)."""
    with httpx.Client(base_url=server_v2_on) as client:
        cookies_a = _register(client, email="user-a@example.com")
        cookies_b = _register(client, email="user-b@example.com")

        # User A creates a key.
        create_a = client.post(
            "/api/keys",
            json={"name": "a-key"},
            cookies=cookies_a,
            headers={"X-CSRF-Token": cookies_a["csrf_token"]},
        )
        assert create_a.status_code == 201, create_a.text
        a_key_id = create_a.json()["id"]

        # User B tries to DELETE A's key → opaque 404 (NOT 403).
        delete_b = client.delete(
            f"/api/keys/{a_key_id}",
            cookies=cookies_b,
            headers={"X-CSRF-Token": cookies_b["csrf_token"]},
        )
        assert delete_b.status_code == 404, delete_b.text


@pytest.mark.integration
def test_register_rate_limit_3_per_hour(server_v2_on: str) -> None:
    """4th register from same /24 returns 429 with Retry-After (ANTI-01)."""
    with httpx.Client(base_url=server_v2_on) as client:
        # 3 successful registers — under the limit. Clear cookie jar between
        # iterations so the persisted session+csrf cookies do NOT cause
        # CsrfMiddleware to reject subsequent POSTs as state-mutating cookie
        # auth without X-CSRF-Token (would mask the rate-limit signal).
        for index in range(3):
            client.cookies.clear()
            response = client.post(
                "/auth/register",
                json={
                    "email": f"rl-user-{index}@example.com",
                    "password": "supersecret123",
                },
            )
            assert response.status_code == 201, (
                f"register #{index} unexpected {response.status_code}: {response.text}"
            )
        # 4th — slowapi rejects with 429 + Retry-After header.
        client.cookies.clear()
        rejected = client.post(
            "/auth/register",
            json={"email": "rl-user-overflow@example.com", "password": "supersecret123"},
        )
        assert rejected.status_code == 429, rejected.text
        retry_after = rejected.headers.get("retry-after") or rejected.headers.get("Retry-After")
        assert retry_after is not None, rejected.headers
        assert int(retry_after) > 0


@pytest.mark.integration
def test_disposable_email_rejected(server_v2_on: str) -> None:
    """Disposable-email domain → 422 generic ``Registration failed`` (ANTI-04)."""
    with httpx.Client(base_url=server_v2_on) as client:
        response = client.post(
            "/auth/register",
            json={"email": "trash@10minutemail.com", "password": "supersecret123"},
        )
        assert response.status_code == 422, response.text
        body = response.json()
        # Anti-enumeration: identical message + code as duplicate-email leg.
        assert "Registration failed" in str(body)


@pytest.mark.integration
def test_cors_preflight_allowed_origin(server_v2_on: str) -> None:
    """Preflight from FRONTEND_URL → ACAO + ACAC=true (ANTI-06)."""
    with httpx.Client(base_url=server_v2_on) as client:
        response = client.options(
            "/auth/register",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.integration
def test_cors_preflight_disallowed_origin(server_v2_on: str) -> None:
    """Preflight from random origin → no ACAO header (ANTI-06)."""
    with httpx.Client(base_url=server_v2_on) as client:
        response = client.options(
            "/auth/register",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # CORSMiddleware does NOT echo the origin for non-allowlisted requests.
        assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"


@pytest.mark.integration
def test_billing_stubs_return_501(server_v2_on: str) -> None:
    """/billing/checkout (auth) + /billing/webhook (sig schema) — BILL-05/06."""
    with httpx.Client(base_url=server_v2_on) as client:
        cookies = _register(client, email="billing@example.com")

        # /billing/checkout — auth required, returns 501 stub.
        checkout = client.post(
            "/billing/checkout",
            json={"plan": "pro"},
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["csrf_token"]},
        )
        assert checkout.status_code == 501, checkout.text
        body = checkout.json()
        assert body.get("status") == "stub"
        assert "v1.3" in body.get("hint", "")

        # /billing/webhook is a Stripe-only public-allowlist endpoint (no auth).
        # Wipe the cookie jar so the persistent session+csrf cookies (set by
        # the prior /billing/checkout cookies= argument) do not flip DualAuth
        # into cookie-auth mode and trigger CsrfMiddleware (which would mask
        # the 501/400 signal we are testing here).
        client.cookies.clear()

        # /billing/webhook — VALID Stripe-Signature schema → 501 stub.
        webhook_ok = client.post(
            "/billing/webhook",
            headers={"Stripe-Signature": "t=1700000000,v1=abc123"},
        )
        assert webhook_ok.status_code == 501, webhook_ok.text

        # /billing/webhook — MALFORMED Stripe-Signature → 400 (rejected before stub).
        client.cookies.clear()
        webhook_bad = client.post(
            "/billing/webhook",
            headers={"Stripe-Signature": "garbage"},
        )
        assert webhook_bad.status_code == 400, webhook_bad.text


@pytest.mark.integration
def test_v2_disabled_routes_not_registered(server_v2_off: str) -> None:
    """V2_OFF: /auth/register NOT registered (404 with valid legacy bearer)."""
    with httpx.Client(base_url=server_v2_off) as client:
        # /health is in PUBLIC_ALLOWLIST in BOTH branches.
        health = client.get("/health")
        assert health.status_code == 200

        # /auth/register requires bearer in V2-OFF (BearerAuthMiddleware) AND
        # is unregistered → with valid bearer the middleware passes, FastAPI
        # router returns 404 (no route matched).
        response = client.post(
            "/auth/register",
            json={"email": "x@example.com", "password": "supersecret123"},
            headers={"Authorization": "Bearer smoke-legacy-token"},
        )
        assert response.status_code == 404, response.text


@pytest.mark.integration
def test_v2_enabled_routes_registered(server_v2_on: str) -> None:
    """V2_ON: /auth/register registered — empty body returns 422 (not 404)."""
    with httpx.Client(base_url=server_v2_on) as client:
        response = client.post("/auth/register", json={})
        # 422 = pydantic validation error (route is registered + body invalid).
        assert response.status_code == 422, response.text


@pytest.mark.integration
def test_csrf_required_on_cookie_post(server_v2_on: str) -> None:
    """Cookie-auth POST without ``X-CSRF-Token`` → 403 (MID-04)."""
    with httpx.Client(base_url=server_v2_on) as client:
        cookies = _register(client, email="csrf@example.com")
        # POST /api/keys WITHOUT X-CSRF-Token header → CsrfMiddleware blocks.
        response = client.post(
            "/api/keys", json={"name": "no-csrf"}, cookies=cookies,
        )
        assert response.status_code == 403, response.text


@pytest.mark.integration
def test_bearer_auth_skips_csrf(server_v2_on: str) -> None:
    """Bearer auth wins resolution → CSRF double-submit not required."""
    with httpx.Client(base_url=server_v2_on) as client:
        cookies = _register(client, email="bearer@example.com")
        # Bootstrap: create one key via cookie + CSRF.
        create_first = client.post(
            "/api/keys",
            json={"name": "bk-bootstrap"},
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["csrf_token"]},
        )
        assert create_first.status_code == 201
        api_key = create_first.json()["key"]

        # Now create a SECOND key via Authorization: Bearer (no CSRF, no cookie)
        # — bearer skips CSRF, so this MUST succeed.
        create_second = client.post(
            "/api/keys",
            json={"name": "bk-bearer"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert create_second.status_code == 201, create_second.text
