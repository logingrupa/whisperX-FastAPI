"""KeyService — creates, verifies, and revokes API keys (KEY-02, KEY-03)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core import api_key
from app.core.exceptions import InvalidApiKeyHashError
from app.core.logging import logger
from app.domain.entities.api_key import ApiKey
from app.domain.repositories.api_key_repository import IApiKeyRepository


class KeyService:
    """Mediates app.core.api_key + IApiKeyRepository.

    create_key() returns the plaintext exactly once — caller (Phase 13
    route handler) is responsible for show-once UX.
    """

    def __init__(self, repository: IApiKeyRepository) -> None:
        self.repository = repository

    def create_key(self, user_id: int, name: str) -> tuple[str, ApiKey]:
        """Generate, persist, and return (plaintext, persisted_api_key).

        Plaintext is shown to the user exactly once (CONTEXT §211 locked).
        """
        plaintext, prefix_value, sha256_hash = api_key.generate()
        key = ApiKey(
            id=None,
            user_id=user_id,
            name=name,
            prefix=prefix_value,
            hash=sha256_hash,
        )
        new_id = self.repository.add(key)
        key.id = new_id
        logger.info(
            "ApiKey created id=%s user_id=%s prefix=%s",
            new_id, user_id, prefix_value,
        )
        return plaintext, key

    def verify_plaintext(self, plaintext: str) -> ApiKey:
        """Resolve a presented plaintext to an active ApiKey.

        - Parses prefix; raises InvalidApiKeyFormatError on shape failure.
        - Looks up active candidates by prefix (indexed).
        - Constant-time hash compare via app.core.api_key.verify.
        - Raises InvalidApiKeyHashError if no candidate matches.
        """
        prefix_value = api_key.parse_prefix(plaintext)
        candidates = self.repository.get_by_prefix(prefix_value)
        for candidate in candidates:
            if api_key.verify(plaintext, candidate.hash):
                self.repository.mark_used(
                    int(candidate.id), datetime.now(timezone.utc)
                )
                logger.debug(
                    "ApiKey verified id=%s prefix=%s",
                    candidate.id, prefix_value,
                )
                return candidate
        logger.debug("ApiKey verify failed prefix=%s", prefix_value)
        raise InvalidApiKeyHashError()

    def revoke_key(self, key_id: int) -> None:
        """Soft-delete an API key."""
        self.repository.revoke(key_id)
        logger.info("ApiKey revoked id=%s", key_id)

    def list_for_user(self, user_id: int) -> list[ApiKey]:
        """Return all keys (active+revoked) for a user."""
        return self.repository.get_by_user(user_id)
