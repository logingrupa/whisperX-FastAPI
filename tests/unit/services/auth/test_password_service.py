"""Unit tests for PasswordService."""

from __future__ import annotations

import pytest

from app.services.auth.password_service import PasswordService


@pytest.mark.unit
class TestPasswordService:
    @pytest.fixture
    def service(self) -> PasswordService:
        return PasswordService()

    def test_hash_then_verify_succeeds(self, service: PasswordService) -> None:
        hashed = service.hash_password("hunter2")
        assert service.verify_password("hunter2", hashed) is True

    def test_verify_wrong_password_returns_false(
        self, service: PasswordService
    ) -> None:
        hashed = service.hash_password("hunter2")
        assert service.verify_password("wrong", hashed) is False

    def test_hash_returns_phc_string(self, service: PasswordService) -> None:
        hashed = service.hash_password("any")
        assert hashed.startswith("$argon2id$")
