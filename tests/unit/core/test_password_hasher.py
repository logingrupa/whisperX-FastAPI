"""Unit tests for app.core.password_hasher.

Per .planning/phases/11-auth-core-modules-services-di/11-02-PLAN.md (Task 2 §B).
Covers AUTH-02: Argon2id password hashing round-trip + malformed-hash safety.
"""

from __future__ import annotations

import pytest

from app.core import password_hasher


@pytest.mark.unit
class TestPasswordHasher:
    def test_hash_returns_phc_string(self) -> None:
        result = password_hasher.hash("test-password-123")
        assert result.startswith("$argon2id$")

    def test_verify_round_trip_succeeds(self) -> None:
        hashed = password_hasher.hash("correct-horse-battery-staple")
        assert password_hasher.verify("correct-horse-battery-staple", hashed) is True

    def test_verify_wrong_password_returns_false(self) -> None:
        hashed = password_hasher.hash("correct")
        assert password_hasher.verify("wrong", hashed) is False

    def test_verify_malformed_hash_returns_false(self) -> None:
        # No silent crash on garbage input — typed False return.
        assert password_hasher.verify("any", "not-a-phc-string") is False

    def test_two_hashes_of_same_input_differ(self) -> None:
        # Random salt — outputs must differ.
        h1 = password_hasher.hash("same-input")
        h2 = password_hasher.hash("same-input")
        assert h1 != h2
