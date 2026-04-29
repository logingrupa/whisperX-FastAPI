"""Stateless wrapper around app.core.password_hasher (PasswordService)."""

from __future__ import annotations

from app.core import password_hasher
from app.core.logging import logger


class PasswordService:
    """Hash and verify passwords. Single responsibility — no storage,
    no user lookup (that lives in AuthService).
    """

    def hash_password(self, plain: str) -> str:
        """Return Argon2id PHC-string hash. Caller passes plain — service
        does NOT log it.
        """
        logger.debug("PasswordService.hash_password called")
        return password_hasher.hash(plain)

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Constant-time verify; returns False on mismatch."""
        return password_hasher.verify(plain, hashed)
