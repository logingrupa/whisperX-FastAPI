"""Unit tests for CsrfService."""

from __future__ import annotations

import pytest

from app.services.auth.csrf_service import CsrfService


@pytest.mark.unit
class TestCsrfService:
    @pytest.fixture
    def service(self) -> CsrfService:
        return CsrfService()

    def test_issue_returns_nonempty_token(self, service: CsrfService) -> None:
        token = service.issue()
        assert isinstance(token, str) and len(token) >= 32

    def test_verify_matching_returns_true(self, service: CsrfService) -> None:
        token = service.issue()
        assert service.verify(token, token) is True

    def test_verify_mismatched_returns_false(self, service: CsrfService) -> None:
        a = service.issue()
        b = service.issue()
        assert service.verify(a, b) is False
