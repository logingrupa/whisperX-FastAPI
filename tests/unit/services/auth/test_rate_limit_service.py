"""Unit tests for RateLimitService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.domain.entities.rate_limit_bucket import RateLimitBucket
from app.services.auth.rate_limit_service import RateLimitService


@pytest.mark.unit
class TestRateLimitService:
    @pytest.fixture
    def mock_repo(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo: MagicMock) -> RateLimitService:
        return RateLimitService(mock_repo)

    def test_first_call_allowed_and_persists(
        self, service: RateLimitService, mock_repo: MagicMock,
    ) -> None:
        mock_repo.get_by_key.return_value = None
        allowed = service.check_and_consume(
            "user:1:hour", tokens_needed=1, rate=0.0, capacity=5,
        )
        assert allowed is True
        mock_repo.upsert_atomic.assert_called_once()
        args, _ = mock_repo.upsert_atomic.call_args
        assert args[0] == "user:1:hour"
        assert args[1]["tokens"] == 4

    def test_exhausted_bucket_denies(
        self, service: RateLimitService, mock_repo: MagicMock,
    ) -> None:
        now = datetime.now(timezone.utc)
        mock_repo.get_by_key.return_value = RateLimitBucket(
            id=1, bucket_key="user:1:hour", tokens=0, last_refill=now,
        )
        allowed = service.check_and_consume(
            "user:1:hour", tokens_needed=1, rate=0.0, capacity=5,
        )
        assert allowed is False

    def test_persistence_called_even_on_denial(
        self, service: RateLimitService, mock_repo: MagicMock,
    ) -> None:
        now = datetime.now(timezone.utc)
        mock_repo.get_by_key.return_value = RateLimitBucket(
            id=1, bucket_key="user:1:hour", tokens=0, last_refill=now,
        )
        service.check_and_consume(
            "user:1:hour", tokens_needed=1, rate=0.0, capacity=5,
        )
        # Bucket state still updated (last_refill bumped).
        mock_repo.upsert_atomic.assert_called_once()
