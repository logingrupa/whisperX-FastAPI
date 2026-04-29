"""Unit tests for DualAuthMiddleware (Phase 13 / MID-01, MID-02, MID-03).

Per .planning/phases/13-atomic-backend-cutover/13-02-PLAN.md Task 1:
13 behaviour cases covering public allowlist, OPTIONS, bearer success/failure,
cookie success/failure (expired/tampered/version-mismatch), WebSocket bypass,
bearer-wins resolution order, and protected-path 401.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core import jwt_codec
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import (
    InvalidApiKeyFormatError,
    InvalidApiKeyHashError,
    JwtExpiredError,
    JwtTamperedError,
)
from app.domain.entities.api_key import ApiKey
from app.domain.entities.user import User

_SECRET = "test-secret-at-least-32-bytes-long!"


def _make_user(user_id: int = 7, plan_tier: str = "trial", token_version: int = 0) -> User:
    return User(
        id=user_id,
        email="user@example.com",
        password_hash="argon2$dummy",
        plan_tier=plan_tier,
        token_version=token_version,
    )


def _make_api_key(key_id: int = 11, user_id: int = 7) -> ApiKey:
    return ApiKey(
        id=key_id,
        user_id=user_id,
        name="default",
        prefix="abcdefgh",
        hash="0" * 64,
    )


def _build_container(
    *,
    user: User | None = None,
    api_key: ApiKey | None = None,
    key_service_raises: Exception | None = None,
    token_service_raises: Exception | None = None,
) -> MagicMock:
    container = MagicMock()

    key_service = MagicMock()
    if key_service_raises is not None:
        key_service.verify_plaintext.side_effect = key_service_raises
    else:
        key_service.verify_plaintext.return_value = api_key
    container.key_service.return_value = key_service

    user_repository = MagicMock()
    user_repository.get_by_id.return_value = user
    container.user_repository.return_value = user_repository

    token_service = MagicMock()
    if token_service_raises is not None:
        token_service.verify_and_refresh.side_effect = token_service_raises
    else:
        # Mirror real behaviour: returns (payload, new_token).
        def _refresh(token: str, current_token_version: int) -> tuple[dict, str]:
            payload = jwt_codec.decode_session(token, secret=_SECRET)
            new_token = jwt_codec.encode_session(
                user_id=int(payload["sub"]),
                token_version=current_token_version,
                secret=_SECRET,
                ttl_days=7,
            )
            return payload, new_token

        token_service.verify_and_refresh.side_effect = _refresh
    container.token_service.return_value = token_service

    return container


def _settings_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch get_settings used by DualAuthMiddleware to a known JWT secret."""
    fake = MagicMock()
    fake.auth.JWT_SECRET.get_secret_value.return_value = _SECRET
    fake.auth.JWT_TTL_DAYS = 7
    fake.auth.COOKIE_SECURE = False
    fake.auth.COOKIE_DOMAIN = ""
    monkeypatch.setattr("app.core.dual_auth.get_settings", lambda: fake)


def _build_app(container: MagicMock) -> Starlette:
    async def protected(request):  # pragma: no cover - exercised in tests
        return JSONResponse(
            {
                "user_id": getattr(request.state.user, "id", None),
                "plan_tier": request.state.plan_tier,
                "auth_method": request.state.auth_method,
                "api_key_id": request.state.api_key_id,
            }
        )

    async def public_health(request):  # pragma: no cover
        return JSONResponse(
            {
                "user_present": request.state.user is not None,
                "auth_method": request.state.auth_method,
            }
        )

    async def public_register(request):  # pragma: no cover
        return JSONResponse({"ok": True})

    routes = [
        Route("/protected", protected, methods=["GET", "POST"]),
        Route("/health", public_health, methods=["GET"]),
        Route("/auth/register", public_register, methods=["POST"]),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(DualAuthMiddleware, container=container)
    return app


@pytest.mark.unit
class TestDualAuthMiddleware:
    def test_public_health_passes_without_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        client = TestClient(_build_app(_build_container()))
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"user_present": False, "auth_method": None}

    def test_public_auth_register_passes_without_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        client = TestClient(_build_app(_build_container()))
        response = client.post("/auth/register", json={"email": "a@b.c", "password": "x"})
        assert response.status_code == 200

    def test_options_preflight_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        client = TestClient(_build_app(_build_container()))
        # No matching route for OPTIONS in our test app — Starlette will 405,
        # but the assertion is that DualAuthMiddleware did not 401.
        response = client.options("/protected")
        assert response.status_code != 401

    def test_bearer_valid_sets_request_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        user = _make_user(user_id=7, plan_tier="pro")
        api_key = _make_api_key(key_id=11, user_id=7)
        container = _build_container(user=user, api_key=api_key)
        client = TestClient(_build_app(container))
        response = client.get(
            "/protected", headers={"Authorization": "Bearer whsk_abcdefgh_0123456789012345678901"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "user_id": 7,
            "plan_tier": "pro",
            "auth_method": "bearer",
            "api_key_id": 11,
        }

    def test_bearer_malformed_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        container = _build_container(
            key_service_raises=InvalidApiKeyFormatError(reason="malformed")
        )
        client = TestClient(_build_app(container))
        response = client.get("/protected", headers={"Authorization": "Bearer broken"})
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}

    def test_bearer_unknown_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        container = _build_container(key_service_raises=InvalidApiKeyHashError())
        client = TestClient(_build_app(container))
        response = client.get(
            "/protected", headers={"Authorization": "Bearer whsk_abcdefgh_unknown_unknown_unknwn"}
        )
        assert response.status_code == 401

    def test_cookie_valid_sets_state_and_refreshes_cookie(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _settings_stub(monkeypatch)
        user = _make_user(user_id=42, token_version=3)
        token = jwt_codec.encode_session(
            user_id=42, token_version=3, secret=_SECRET, ttl_days=7
        )
        container = _build_container(user=user)
        client = TestClient(_build_app(container))
        response = client.get("/protected", cookies={"session": token})
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == 42
        assert body["auth_method"] == "cookie"
        assert body["api_key_id"] is None
        # Sliding refresh — Set-Cookie header re-issues session.
        assert "session=" in response.headers.get("set-cookie", "")

    def test_cookie_expired_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        expired = pyjwt.encode(
            {"sub": "1", "exp": int(past.timestamp()), "ver": 0, "method": "session"},
            _SECRET,
            algorithm="HS256",
        )
        container = _build_container(user=_make_user(user_id=1))
        client = TestClient(_build_app(container))
        response = client.get("/protected", cookies={"session": expired})
        assert response.status_code == 401

    def test_cookie_tampered_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        token = jwt_codec.encode_session(
            user_id=1, token_version=0, secret=_SECRET, ttl_days=7
        )
        tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
        container = _build_container(user=_make_user(user_id=1))
        client = TestClient(_build_app(container))
        response = client.get("/protected", cookies={"session": tampered})
        assert response.status_code == 401

    def test_cookie_token_version_mismatch_returns_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _settings_stub(monkeypatch)
        token = jwt_codec.encode_session(
            user_id=1, token_version=0, secret=_SECRET, ttl_days=7
        )
        container = _build_container(
            user=_make_user(user_id=1, token_version=5),
            token_service_raises=JwtTamperedError("token version mismatch"),
        )
        client = TestClient(_build_app(container))
        response = client.get("/protected", cookies={"session": token})
        assert response.status_code == 401

    def test_cookie_user_missing_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        token = jwt_codec.encode_session(
            user_id=99, token_version=0, secret=_SECRET, ttl_days=7
        )
        container = _build_container(user=None)  # user_repository.get_by_id → None
        client = TestClient(_build_app(container))
        response = client.get("/protected", cookies={"session": token})
        assert response.status_code == 401

    def test_bearer_wins_when_both_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _settings_stub(monkeypatch)
        user = _make_user(user_id=7, plan_tier="pro")
        api_key = _make_api_key(key_id=11, user_id=7)
        container = _build_container(user=user, api_key=api_key)
        client = TestClient(_build_app(container))
        # Cookie present + bearer present — bearer should win (auth_method=bearer).
        token = jwt_codec.encode_session(
            user_id=7, token_version=0, secret=_SECRET, ttl_days=7
        )
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer whsk_abcdefgh_0123456789012345678901"},
            cookies={"session": token},
        )
        assert response.status_code == 200
        assert response.json()["auth_method"] == "bearer"

    def test_no_auth_on_protected_path_returns_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _settings_stub(monkeypatch)
        client = TestClient(_build_app(_build_container()))
        response = client.get("/protected")
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}
        assert response.headers.get("WWW-Authenticate", "").lower().startswith("bearer")

    def test_bearer_with_no_user_for_key_returns_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _settings_stub(monkeypatch)
        api_key = _make_api_key(key_id=11, user_id=7)
        container = _build_container(user=None, api_key=api_key)  # user lookup misses
        client = TestClient(_build_app(container))
        response = client.get(
            "/protected", headers={"Authorization": "Bearer whsk_abcdefgh_0123456789012345678901"}
        )
        assert response.status_code == 401

    def test_logger_does_not_emit_raw_token(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """T-13-04 — logging discipline: never emit raw token / plaintext key."""
        _settings_stub(monkeypatch)
        plaintext = "whsk_abcdefgh_supersecretbody12345678"
        token = jwt_codec.encode_session(
            user_id=7, token_version=0, secret=_SECRET, ttl_days=7
        )
        user = _make_user(user_id=7)
        api_key = _make_api_key(key_id=11, user_id=7)
        container = _build_container(user=user, api_key=api_key)
        client = TestClient(_build_app(container))
        with caplog.at_level(logging.DEBUG, logger="app.core.dual_auth"):
            client.get("/protected", headers={"Authorization": f"Bearer {plaintext}"})
            client.get("/protected", cookies={"session": token})
        joined = "\n".join(rec.getMessage() for rec in caplog.records)
        assert plaintext not in joined
        assert token not in joined
