"""Wraps app.core.jwt_codec; issues sliding-expiry session tokens (TokenService)."""

from __future__ import annotations

from typing import Any

from app.core import jwt_codec
from app.core.exceptions import JwtTamperedError
from app.core.logging import logger


class TokenService:
    """Issue and refresh HS256 session tokens.

    Constructor takes the JWT secret; the DI container binds it from
    ``config.provided.auth.JWT_SECRET`` so this class stays pure (no
    ``Settings()`` lookup at call time).
    """

    def __init__(self, secret: str, ttl_days: int = 7) -> None:
        self.secret = secret
        self.ttl_days = ttl_days

    def issue(self, user_id: int, token_version: int) -> str:
        """Encode a fresh HS256 session token."""
        logger.debug("TokenService.issue user_id=%s", user_id)
        return jwt_codec.encode_session(
            user_id=user_id,
            token_version=token_version,
            secret=self.secret,
            ttl_days=self.ttl_days,
        )

    def verify_and_refresh(
        self,
        token: str,
        current_token_version: int,
    ) -> tuple[dict[str, Any], str]:
        """Decode + check token_version + issue a fresh token (sliding expiry).

        Raises JwtExpiredError / JwtAlgorithmError / JwtTamperedError on
        decode failures, or JwtTamperedError on token_version mismatch.
        """
        payload = jwt_codec.decode_session(token, secret=self.secret)
        if payload.get("ver") != current_token_version:
            raise JwtTamperedError("token version mismatch")
        # Per RFC 7519 §4.1.2 sub is a string on the wire; recover int here.
        new_token = self.issue(int(payload["sub"]), current_token_version)
        return payload, new_token
