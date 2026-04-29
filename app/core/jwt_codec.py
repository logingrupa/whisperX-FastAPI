"""Single source of truth for JWT encode/decode.

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §62-71 (locked):
- HS256 only — algorithms=["HS256"] always.
- Token shape: {"sub","iat","exp","ver","method"}.
- Verifier greps `jwt.decode(` across app/ — only this module may match.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.exceptions import JwtAlgorithmError, JwtExpiredError, JwtTamperedError

_ALGORITHM = "HS256"
_METHOD = "session"
assert _ALGORITHM == "HS256", "JWT algorithm drift"
assert _METHOD == "session", "JWT method drift"


def encode_session(
    *,
    user_id: int,
    token_version: int,
    secret: str,
    ttl_days: int = 7,
) -> str:
    """Encode an HS256 session token. Caller supplies the secret.

    Note: per RFC 7519 §4.1.2 the `sub` claim MUST be a case-sensitive string;
    PyJWT 2.x enforces this. We serialize user_id as ``str(user_id)`` on the
    wire. Callers of ``decode_session`` recover the int via ``int(payload["sub"])``.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl_days)).timestamp()),
        "ver": token_version,
        "method": _METHOD,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_session(token: str, *, secret: str) -> dict[str, Any]:
    """Decode an HS256 session token. Maps PyJWT errors to typed app exceptions.

    THE ONLY `jwt.decode(...)` CALL IN app/. Verifier enforces this.
    """
    try:
        return jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise JwtExpiredError() from e
    except jwt.InvalidAlgorithmError as e:
        raise JwtAlgorithmError(str(e)) from e
    except jwt.InvalidTokenError as e:
        raise JwtTamperedError(str(e)) from e
