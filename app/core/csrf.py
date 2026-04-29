"""Double-submit CSRF token generate + verify.

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §104-109 (locked):
- 32 random bytes, urlsafe-base64 encoded.
- Verify: secrets.compare_digest of cookie token vs header token.
- Bearer-authenticated routes skip CSRF (Phase 13 middleware concern).
"""

from __future__ import annotations

import secrets

_TOKEN_BYTES = 32
assert _TOKEN_BYTES == 32, "CSRF token byte-length drift"


def generate() -> str:
    """Return a fresh urlsafe-base64 CSRF token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def verify(cookie_token: str, header_token: str) -> bool:
    """Constant-time double-submit compare. Empty-string inputs return False."""
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)
