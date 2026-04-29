"""Unit tests for RateLimitService.release() — W1 fix (Phase 13-08).

Coverage (≥4):
  1. test_release_refunds_one_token       — consume + release returns to capacity
  2. test_release_caps_at_capacity        — never overflows beyond capacity
  3. test_release_noop_when_bucket_missing — defensive: no crash, no upsert
  4. test_release_concurrent_bucket_round_trip — full RED→GREEN cycle
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.domain.entities.rate_limit_bucket import RateLimitBucket
from app.services.auth.rate_limit_service import RateLimitService


@pytest.mark.unit
class TestRateLimitServiceRelease:
    @pytest.fixture
    def mock_repo(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo: MagicMock) -> RateLimitService:
        return RateLimitService(mock_repo)

    def test_release_refunds_one_token(
        self, service: RateLimitService, mock_repo: MagicMock
    ) -> None:
        """consume(capacity=1) -> tokens=0 -> release() -> tokens=1."""
        now = datetime.now(timezone.utc)
        mock_repo.get_by_key.return_value = RateLimitBucket(
            id=1, bucket_key="user:1:concurrent", tokens=0, last_refill=now,
        )
        service.release("user:1:concurrent", tokens=1, capacity=1)
        mock_repo.upsert_atomic.assert_called_once()
        args, _ = mock_repo.upsert_atomic.call_args
        assert args[0] == "user:1:concurrent"
        assert args[1]["tokens"] == 1

    def test_release_caps_at_capacity(
        self, service: RateLimitService, mock_repo: MagicMock
    ) -> None:
        """Release on a full bucket stays at capacity (no overflow)."""
        now = datetime.now(timezone.utc)
        mock_repo.get_by_key.return_value = RateLimitBucket(
            id=1, bucket_key="user:1:concurrent", tokens=3, last_refill=now,
        )
        service.release("user:1:concurrent", tokens=1, capacity=3)
        mock_repo.upsert_atomic.assert_called_once()
        args, _ = mock_repo.upsert_atomic.call_args
        assert args[1]["tokens"] == 3  # capped, not 4

    def test_release_noop_when_bucket_missing(
        self, service: RateLimitService, mock_repo: MagicMock
    ) -> None:
        """Release on unknown key -> no error, no upsert."""
        mock_repo.get_by_key.return_value = None
        service.release("user:99:concurrent", tokens=1, capacity=1)
        mock_repo.upsert_atomic.assert_not_called()

    def test_release_concurrent_bucket_round_trip(
        self, service: RateLimitService, mock_repo: MagicMock
    ) -> None:
        """consume -> release -> consume succeeds (full cycle for concurrency).

        Simulates the real flow: hold a slot during transcription, release
        on completion, next transcribe consumes the refunded slot.
        """
        now = datetime.now(timezone.utc)

        # 1. Initial consume (capacity=1, tokens go 1 -> 0)
        mock_repo.get_by_key.return_value = None
        first = service.check_and_consume(
            "user:1:concurrent", tokens_needed=1, rate=0.0, capacity=1,
        )
        assert first is True

        # 2. Release — repo reports the consumed bucket
        mock_repo.get_by_key.return_value = RateLimitBucket(
            id=1, bucket_key="user:1:concurrent", tokens=0, last_refill=now,
        )
        service.release("user:1:concurrent", tokens=1, capacity=1)

        # 3. Second consume — slot was returned, succeeds
        mock_repo.get_by_key.return_value = RateLimitBucket(
            id=1, bucket_key="user:1:concurrent", tokens=1, last_refill=now,
        )
        second = service.check_and_consume(
            "user:1:concurrent", tokens_needed=1, rate=0.0, capacity=1,
        )
        assert second is True

    def test_release_default_args(
        self, service: RateLimitService, mock_repo: MagicMock
    ) -> None:
        """release() with no kwargs: tokens=1, capacity=1 defaults."""
        now = datetime.now(timezone.utc)
        mock_repo.get_by_key.return_value = RateLimitBucket(
            id=1, bucket_key="x", tokens=0, last_refill=now,
        )
        service.release("x")
        args, _ = mock_repo.upsert_atomic.call_args
        assert args[1]["tokens"] == 1
