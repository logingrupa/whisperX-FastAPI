"""Unit tests for legacy request.state auth helpers in app.api.dependencies.

Covers ``get_authenticated_user`` + ``get_current_user_id`` — helpers that
read pre-populated ``request.state.user`` from the v1.1 audio routes
(audio_api.py, audio_services_api.py). These helpers stay until Plan 19-13
sweeps the last v1.1 callers.

Originally lived in tests/unit/core/test_csrf_middleware.py; relocated in
Plan 19-12 when CsrfMiddleware (and its tests) were deleted. Coverage of
the helpers is preserved verbatim — class name and assertions unchanged.
"""

from __future__ import annotations

import pytest


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
