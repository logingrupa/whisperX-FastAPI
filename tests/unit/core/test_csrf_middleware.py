"""Unit tests for CsrfMiddleware (Phase 13 / MID-04).

Per .planning/phases/13-atomic-backend-cutover/13-02-PLAN.md Task 2:
9 behaviour cases covering GET-bypass, cookie-success, missing/mismatched
header → 403, bearer-skip, PUT/PATCH/DELETE enforcement, OPTIONS-bypass,
public-allowlist (no auth_method) → bypass.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.csrf_middleware import CsrfMiddleware


def _build_container(verify_returns: bool = True) -> MagicMock:
    container = MagicMock()
    csrf_service = MagicMock()
    csrf_service.verify.return_value = verify_returns
    container.csrf_service.return_value = csrf_service
    return container


class _StateInjector(BaseHTTPMiddleware):
    """Tiny preceding middleware that stamps ``request.state.auth_method``.

    In production this is set by DualAuthMiddleware; for unit tests we inject
    it directly so CsrfMiddleware sees the contract it expects.
    """

    def __init__(self, app, *, auth_method):
        super().__init__(app)
        self._auth_method = auth_method

    async def dispatch(self, request, call_next):
        request.state.auth_method = self._auth_method
        return await call_next(request)


def _build_app(*, auth_method, verify_returns: bool = True) -> Starlette:
    async def echo(request):  # pragma: no cover - exercised in tests
        return JSONResponse({"ok": True})

    routes = [
        Route("/protected", echo, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
    ]
    app = Starlette(routes=routes)
    # Order matters: outermost (last add) runs FIRST. We want:
    #   _StateInjector  → CsrfMiddleware  → endpoint
    # Therefore add CsrfMiddleware first, then _StateInjector.
    app.add_middleware(CsrfMiddleware, container=_build_container(verify_returns))
    app.add_middleware(_StateInjector, auth_method=auth_method)
    return app


@pytest.mark.unit
class TestCsrfMiddleware:
    def test_get_with_cookie_auth_no_header_passes(self) -> None:
        app = _build_app(auth_method="cookie")
        client = TestClient(app)
        response = client.get("/protected", cookies={"csrf_token": "abc"})
        assert response.status_code == 200

    def test_post_cookie_auth_valid_csrf_passes(self) -> None:
        app = _build_app(auth_method="cookie", verify_returns=True)
        client = TestClient(app)
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "abc"},
            cookies={"csrf_token": "abc"},
        )
        assert response.status_code == 200

    def test_post_cookie_auth_missing_csrf_returns_403(self) -> None:
        app = _build_app(auth_method="cookie")
        client = TestClient(app)
        response = client.post("/protected", cookies={"csrf_token": "abc"})
        assert response.status_code == 403
        assert response.json() == {"detail": "CSRF token missing"}

    def test_post_cookie_auth_mismatched_csrf_returns_403(self) -> None:
        app = _build_app(auth_method="cookie", verify_returns=False)
        client = TestClient(app)
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "wrong"},
            cookies={"csrf_token": "abc"},
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "CSRF token mismatch"}

    def test_post_bearer_auth_skips_csrf(self) -> None:
        app = _build_app(auth_method="bearer")
        client = TestClient(app)
        # No X-CSRF-Token header — must still pass for bearer.
        response = client.post("/protected")
        assert response.status_code == 200

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    def test_state_mutating_methods_enforce_csrf_under_cookie_auth(
        self, method: str
    ) -> None:
        app = _build_app(auth_method="cookie")
        client = TestClient(app)
        response = client.request(method, "/protected", cookies={"csrf_token": "abc"})
        assert response.status_code == 403

    def test_options_passes(self) -> None:
        app = _build_app(auth_method="cookie")
        client = TestClient(app)
        response = client.options("/protected")
        # OPTIONS is exempt; not 403 — Starlette may 405 if method not declared,
        # the assertion is only that CsrfMiddleware did not 403.
        assert response.status_code != 403

    def test_public_path_no_auth_method_skips_csrf(self) -> None:
        app = _build_app(auth_method=None)
        client = TestClient(app)
        response = client.post("/protected")
        assert response.status_code == 200

    def test_get_head_bypass(self) -> None:
        app = _build_app(auth_method="cookie")
        client = TestClient(app)
        # HEAD on /protected (route declared GET) — Starlette serves HEAD via GET.
        response = client.head("/protected")
        assert response.status_code != 403


@pytest.mark.unit
class TestGetAuthenticatedUser:
    def test_returns_user_when_state_populated(self) -> None:
        from starlette.requests import Request

        from app.api.dependencies import get_authenticated_user
        from app.domain.entities.user import User

        user = User(
            id=7,
            email="x@y.z",
            password_hash="argon2$x",
            plan_tier="trial",
            token_version=0,
        )
        scope = {"type": "http", "headers": []}
        request = Request(scope)
        request.state.user = user
        assert get_authenticated_user(request) is user

    def test_raises_401_when_state_empty(self) -> None:
        from fastapi import HTTPException
        from starlette.requests import Request

        from app.api.dependencies import get_authenticated_user

        scope = {"type": "http", "headers": []}
        request = Request(scope)
        request.state.user = None
        with pytest.raises(HTTPException) as exc:
            get_authenticated_user(request)
        assert exc.value.status_code == 401

    def test_get_current_user_id_returns_int(self) -> None:
        from starlette.requests import Request

        from app.api.dependencies import get_current_user_id
        from app.domain.entities.user import User

        user = User(
            id=7,
            email="x@y.z",
            password_hash="argon2$x",
            plan_tier="trial",
            token_version=0,
        )
        scope = {"type": "http", "headers": []}
        request = Request(scope)
        request.state.user = user
        assert get_current_user_id(request) == 7
