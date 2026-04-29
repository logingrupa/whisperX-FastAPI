"""whsk_<prefix>_<body> API key generate/verify/parse.

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §72-82 (locked):
- 36-char total: ``whsk_`` + 8-char prefix + ``_`` + 22-char body.
- 8-char prefix indexed (idx_api_keys_prefix from Phase 10).
- SHA-256 hex hash storage; secrets.compare_digest verify.
"""

from __future__ import annotations

import secrets

from app.core._hashing import _sha256_hex
from app.core.exceptions import InvalidApiKeyFormatError

_KEY_PREFIX = "whsk_"
_PREFIX_LENGTH = 8
_BODY_LENGTH = 22
# whsk_(5) + prefix(8) + _(1) + body(22) = 36
_TOTAL_LENGTH = len(_KEY_PREFIX) + _PREFIX_LENGTH + 1 + _BODY_LENGTH

# Tiger-style invariants — fail loudly at module load if format drifts.
assert _TOTAL_LENGTH == 36, "API key total length drift"
assert _PREFIX_LENGTH == 8, "API key prefix length drift"
assert _BODY_LENGTH == 22, "API key body length drift"
assert _KEY_PREFIX == "whsk_", "API key literal prefix drift"


def generate() -> tuple[str, str, str]:
    """Return (plaintext, prefix, sha256_hex) for a freshly minted key.

    Plaintext is shown to the user exactly once at creation time;
    server stores only the prefix (for indexed lookup) and hash.
    """
    body = secrets.token_urlsafe(16)[:_BODY_LENGTH]  # 22 chars urlsafe-base64
    prefix = secrets.token_urlsafe(8)[:_PREFIX_LENGTH]  # 8 chars urlsafe-base64
    plaintext = f"{_KEY_PREFIX}{prefix}_{body}"
    assert len(plaintext) == _TOTAL_LENGTH, "Generated key length drift"
    return plaintext, prefix, _sha256_hex(plaintext)


def verify(plaintext: str, stored_hash: str) -> bool:
    """Constant-time SHA-256 hash compare."""
    return secrets.compare_digest(_sha256_hex(plaintext), stored_hash)


def parse_prefix(plaintext: str) -> str:
    """Extract the 8-char prefix; raise on malformed input."""
    if not plaintext.startswith(_KEY_PREFIX):
        raise InvalidApiKeyFormatError(reason="missing whsk_ prefix")
    if len(plaintext) != _TOTAL_LENGTH:
        raise InvalidApiKeyFormatError(
            reason=f"length {len(plaintext)} != {_TOTAL_LENGTH}"
        )
    return plaintext[len(_KEY_PREFIX) : len(_KEY_PREFIX) + _PREFIX_LENGTH]
