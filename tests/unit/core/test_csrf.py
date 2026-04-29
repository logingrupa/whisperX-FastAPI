"""Unit tests for app.core.csrf.

Per .planning/phases/11-auth-core-modules-services-di/11-02-PLAN.md (Task 2 §E).
Covers double-submit constant-time CSRF token verify (CONTEXT §104-109).
"""

from __future__ import annotations

import pytest

from app.core import csrf


@pytest.mark.unit
class TestCsrf:
    def test_generate_returns_nonempty_token(self) -> None:
        token = csrf.generate()
        assert isinstance(token, str)
        assert len(token) >= 32  # urlsafe-base64 of 32 bytes is ~43 chars

    def test_verify_matching_tokens_returns_true(self) -> None:
        token = csrf.generate()
        assert csrf.verify(token, token) is True

    def test_verify_mismatched_tokens_returns_false(self) -> None:
        a = csrf.generate()
        b = csrf.generate()
        assert csrf.verify(a, b) is False

    def test_verify_empty_string_returns_false(self) -> None:
        token = csrf.generate()
        assert csrf.verify("", token) is False
        assert csrf.verify(token, "") is False
