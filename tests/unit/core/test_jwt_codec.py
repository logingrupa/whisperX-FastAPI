"""Unit tests for app.core.jwt_codec.

Per .planning/phases/11-auth-core-modules-services-di/11-02-PLAN.md (Task 2 §C).
Covers AUTH-08 (HS256-only single decode site) and pre-stages VERIFY-02/03/04
(alg=none rejected, tampered rejected, expired rejected).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from app.core import jwt_codec
from app.core.exceptions import JwtAlgorithmError, JwtExpiredError, JwtTamperedError

_SECRET = "test-secret-do-not-ship"


@pytest.mark.unit
class TestJwtCodec:
    def test_encode_then_decode_round_trip(self) -> None:
        token = jwt_codec.encode_session(
            user_id=42, token_version=0, secret=_SECRET, ttl_days=7,
        )
        payload = jwt_codec.decode_session(token, secret=_SECRET)
        # RFC 7519 §4.1.2: `sub` is a case-sensitive string on the wire.
        # Caller recovers the int via int(payload["sub"]).
        assert payload["sub"] == "42"
        assert int(payload["sub"]) == 42
        assert payload["ver"] == 0
        assert payload["method"] == "session"

    def test_decode_alg_none_token_is_rejected(self) -> None:
        # Forge an alg=none token manually (sub as str — PyJWT 2.12 enforces RFC 7519).
        forged = pyjwt.encode({"sub": "1"}, "", algorithm="none")
        with pytest.raises((JwtAlgorithmError, JwtTamperedError)):
            jwt_codec.decode_session(forged, secret=_SECRET)

    def test_decode_tampered_signature_is_rejected(self) -> None:
        token = jwt_codec.encode_session(user_id=1, token_version=0, secret=_SECRET)
        tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
        with pytest.raises(JwtTamperedError):
            jwt_codec.decode_session(tampered, secret=_SECRET)

    def test_decode_expired_token_is_rejected(self) -> None:
        # Hand-craft an already-expired payload via PyJWT directly.
        # `sub` is str per RFC 7519 §4.1.2 (PyJWT 2.x enforces).
        past = datetime.now(timezone.utc) - timedelta(days=1)
        expired = pyjwt.encode(
            {"sub": "1", "exp": int(past.timestamp()), "ver": 0, "method": "session"},
            _SECRET, algorithm="HS256",
        )
        with pytest.raises(JwtExpiredError):
            jwt_codec.decode_session(expired, secret=_SECRET)

    def test_decode_with_wrong_secret_is_rejected(self) -> None:
        token = jwt_codec.encode_session(user_id=1, token_version=0, secret=_SECRET)
        with pytest.raises(JwtTamperedError):
            jwt_codec.decode_session(token, secret="other-secret")
