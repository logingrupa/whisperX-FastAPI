"""Unit tests for TokenService."""

from __future__ import annotations

import pytest

from app.core.exceptions import JwtTamperedError
from app.services.auth.token_service import TokenService


@pytest.mark.unit
class TestTokenService:
    @pytest.fixture
    def service(self) -> TokenService:
        return TokenService(secret="test-secret-at-least-32-bytes-long!", ttl_days=7)

    def test_issue_returns_token_string(self, service: TokenService) -> None:
        token = service.issue(user_id=42, token_version=0)
        assert isinstance(token, str) and len(token) > 0

    def test_verify_and_refresh_round_trip(self, service: TokenService) -> None:
        token = service.issue(user_id=42, token_version=0)
        payload, new_token = service.verify_and_refresh(
            token, current_token_version=0
        )
        # Per RFC 7519 §4.1.2 sub is a string; caller-side recovery is int().
        assert int(payload["sub"]) == 42
        assert payload["ver"] == 0
        assert isinstance(new_token, str)

    def test_token_version_mismatch_raises(self, service: TokenService) -> None:
        token = service.issue(user_id=42, token_version=0)
        with pytest.raises(JwtTamperedError):
            service.verify_and_refresh(token, current_token_version=1)

    def test_refresh_issues_decodable_token(self, service: TokenService) -> None:
        token = service.issue(user_id=42, token_version=0)
        _, new_token = service.verify_and_refresh(token, current_token_version=0)
        # New token may equal original if issued in the same second; assert it
        # decodes successfully rather than asserting inequality.
        payload, _ = service.verify_and_refresh(new_token, current_token_version=0)
        assert int(payload["sub"]) == 42
