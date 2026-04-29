"""Shared cryptographic primitives — DRY reuse across api_key/csrf/device_fingerprint.

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §150 (locked):
- _sha256_hex MUST be defined exactly once in app/.
- Verifier greps `def _sha256_hex` across app/ — must return exactly 1 hit.
"""

from __future__ import annotations

import hashlib

# Tiger-style invariant — fail loudly at module load.
_DIGEST_HEX_LENGTH = 64
assert _DIGEST_HEX_LENGTH == 64, "SHA-256 hex digest length drift"


def _sha256_hex(s: str) -> str:
    """Return SHA-256 hex digest (64 chars) of UTF-8-encoded input.

    Args:
        s: Input string to hash.

    Returns:
        64-char hex digest.
    """
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
