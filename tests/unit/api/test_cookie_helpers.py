"""Unit tests for app.api._cookie_helpers — DRY cookie clearing (Phase 15-01)."""

from __future__ import annotations

import pytest
from fastapi import Response

from app.api._cookie_helpers import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    clear_auth_cookies,
)


@pytest.mark.unit
def test_clear_auth_cookies_emits_max_age_zero_for_both_cookies() -> None:
    """clear_auth_cookies stamps Max-Age=0 deletes for session + csrf cookies."""
    response = Response()
    clear_auth_cookies(response)
    cookie_headers = [
        value.decode("ascii").lower()
        for name, value in response.raw_headers
        if name == b"set-cookie"
    ]
    joined = "\n".join(cookie_headers)
    assert "session=" in joined
    assert "csrf_token=" in joined
    assert joined.count("max-age=0") == 2


@pytest.mark.unit
def test_cookie_constants_are_locked_strings() -> None:
    """SESSION_COOKIE/CSRF_COOKIE constants are the public single source of truth."""
    assert SESSION_COOKIE == "session"
    assert CSRF_COOKIE == "csrf_token"
