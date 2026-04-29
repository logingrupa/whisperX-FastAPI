"""Unit tests for app.core.api_key.

Per .planning/phases/11-auth-core-modules-services-di/11-02-PLAN.md (Task 2 §D).
Covers KEY-02 (whsk_<8>_<22> 36-char format) + KEY-03 (SHA-256 hash storage).
"""

from __future__ import annotations

import pytest

from app.core import api_key
from app.core.exceptions import InvalidApiKeyFormatError


@pytest.mark.unit
class TestApiKey:
    def test_generate_format_and_lengths(self) -> None:
        plaintext, prefix, hashed = api_key.generate()
        assert plaintext.startswith("whsk_")
        assert len(plaintext) == 36
        assert len(prefix) == 8
        assert len(hashed) == 64  # SHA-256 hex

    def test_verify_correct_plaintext_returns_true(self) -> None:
        plaintext, _, hashed = api_key.generate()
        assert api_key.verify(plaintext, hashed) is True

    def test_verify_wrong_plaintext_returns_false(self) -> None:
        plaintext, _, hashed = api_key.generate()
        assert api_key.verify(plaintext + "tamper", hashed) is False

    def test_parse_prefix_returns_8_char_prefix(self) -> None:
        plaintext, prefix, _ = api_key.generate()
        assert api_key.parse_prefix(plaintext) == prefix

    def test_parse_prefix_rejects_malformed(self) -> None:
        with pytest.raises(InvalidApiKeyFormatError):
            api_key.parse_prefix("not-a-key")
        with pytest.raises(InvalidApiKeyFormatError):
            api_key.parse_prefix("whsk_short")  # length wrong
