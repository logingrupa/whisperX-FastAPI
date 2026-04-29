"""CsrfService — issues + verifies double-submit CSRF tokens."""

from __future__ import annotations

from app.core import csrf


class CsrfService:
    """Stateless double-submit CSRF helper. Singleton in DI Container."""

    def issue(self) -> str:
        """Return a fresh CSRF token (urlsafe-base64 of 32 random bytes)."""
        return csrf.generate()

    def verify(self, cookie_token: str, header_token: str) -> bool:
        """Constant-time double-submit compare."""
        return csrf.verify(cookie_token, header_token)
