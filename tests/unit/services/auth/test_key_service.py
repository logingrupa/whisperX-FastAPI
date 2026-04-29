"""Unit tests for KeyService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import InvalidApiKeyHashError
from app.domain.entities.api_key import ApiKey
from app.services.auth.key_service import KeyService


@pytest.mark.unit
class TestKeyService:
    @pytest.fixture
    def mock_repo(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo: MagicMock) -> KeyService:
        return KeyService(mock_repo)

    def test_create_key_returns_plaintext_and_persists(
        self, service: KeyService, mock_repo: MagicMock,
    ) -> None:
        mock_repo.add.return_value = 99
        plaintext, key = service.create_key(user_id=1, name="cli")
        assert plaintext.startswith("whsk_")
        assert len(plaintext) == 36
        assert key.id == 99
        assert key.user_id == 1
        mock_repo.add.assert_called_once()

    def test_verify_plaintext_success(
        self, service: KeyService, mock_repo: MagicMock,
    ) -> None:
        # Round-trip via the real api_key module: generate, then verify.
        from app.core import api_key as core_api_key

        plaintext, prefix, hashed = core_api_key.generate()
        key = ApiKey(
            id=1, user_id=1, name="n", prefix=prefix, hash=hashed,
        )
        mock_repo.get_by_prefix.return_value = [key]
        result = service.verify_plaintext(plaintext)
        assert result.id == 1
        mock_repo.mark_used.assert_called_once()

    def test_verify_plaintext_no_match_raises(
        self, service: KeyService, mock_repo: MagicMock,
    ) -> None:
        from app.core import api_key as core_api_key

        plaintext, _, _ = core_api_key.generate()
        # Repo returns a key with a *different* hash → no match.
        decoy = ApiKey(
            id=1, user_id=1, name="n", prefix="abcdefgh", hash="0" * 64,
        )
        mock_repo.get_by_prefix.return_value = [decoy]
        with pytest.raises(InvalidApiKeyHashError):
            service.verify_plaintext(plaintext)

    def test_revoke_key_calls_repo(
        self, service: KeyService, mock_repo: MagicMock,
    ) -> None:
        service.revoke_key(42)
        mock_repo.revoke.assert_called_once_with(42)
