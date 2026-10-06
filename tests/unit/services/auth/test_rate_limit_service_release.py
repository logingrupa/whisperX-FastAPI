"""Unit tests for RateLimitService.release() — W1 fix (Phase 13-08).

Coverage (≥4):
  1. test_release_refunds_one_token       — consume + release returns to capacity
  2. test_release_caps_at_capacity        — never overflows beyond capacity
  3. test_release_noop_when_bucket_missing — defensive: no crash, no write
  4. test_release_concurrent_bucket_round_trip — full RED→GREEN cycle
"""

from __future__ import annotations

import pytest

from app.services.auth.rate_limit_service import RateLimitService

from .conftest import InMemoryBucketRepository


@pytest.mark.unit
class TestRateLimitServiceRelease:
    @pytest.fixture
    def service(self, bucket_repository: InMemoryBucketRepository) -> RateLimitService:
        return RateLimitService(bucket_repository)

    def test_release_refunds_one_token(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository
    ) -> None:
        """consume(capacity=1) -> tokens=0 -> release() -> tokens=1."""
        bucket_repository.seed("user:1:concurrent", tokens=0)
        service.release("user:1:concurrent", tokens=1, capacity=1)
        assert bucket_repository.write_count == 1
        assert bucket_repository.buckets["user:1:concurrent"].tokens == 1

    def test_release_caps_at_capacity(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository
    ) -> None:
        """Release on a full bucket stays at capacity (no overflow)."""
        bucket_repository.seed("user:1:concurrent", tokens=3)
        service.release("user:1:concurrent", tokens=1, capacity=3)
        assert bucket_repository.buckets["user:1:concurrent"].tokens == 3  # capped, not 4

    def test_release_noop_when_bucket_missing(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository
    ) -> None:
        """Release on unknown key -> no error, no write."""
        service.release("user:99:concurrent", tokens=1, capacity=1)
        assert bucket_repository.write_count == 0
        assert "user:99:concurrent" not in bucket_repository.buckets

    def test_release_concurrent_bucket_round_trip(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository
    ) -> None:
        """consume -> release -> consume succeeds (full cycle for concurrency).

        Simulates the real flow: hold a slot during transcription, release
        on completion, next transcribe consumes the refunded slot.
        """
        first = service.check_and_consume(
            "user:1:concurrent", tokens_needed=1, rate=0.0, capacity=1,
        )
        blocked = service.check_and_consume(
            "user:1:concurrent", tokens_needed=1, rate=0.0, capacity=1,
        )
        service.release("user:1:concurrent", tokens=1, capacity=1)
        second = service.check_and_consume(
            "user:1:concurrent", tokens_needed=1, rate=0.0, capacity=1,
        )

        assert (first, blocked, second) == (True, False, True)

    def test_release_default_args(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository
    ) -> None:
        """release() with no kwargs: tokens=1, capacity=1 defaults."""
        bucket_repository.seed("x", tokens=0)
        service.release("x")
        assert bucket_repository.buckets["x"].tokens == 1
