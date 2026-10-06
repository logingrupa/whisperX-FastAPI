"""Unit tests for RateLimitService."""

from __future__ import annotations

import pytest

from app.services.auth.rate_limit_service import RateLimitService

from .conftest import InMemoryBucketRepository


@pytest.mark.unit
class TestRateLimitService:
    @pytest.fixture
    def service(self, bucket_repository: InMemoryBucketRepository) -> RateLimitService:
        return RateLimitService(bucket_repository)

    def test_first_call_allowed_and_persists(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository,
    ) -> None:
        allowed = service.check_and_consume(
            "user:1:hour", tokens_needed=1, rate=0.0, capacity=5,
        )
        assert allowed is True
        assert bucket_repository.write_count == 1
        assert bucket_repository.buckets["user:1:hour"].tokens == 4

    def test_exhausted_bucket_denies(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository,
    ) -> None:
        bucket_repository.seed("user:1:hour", tokens=0)
        allowed = service.check_and_consume(
            "user:1:hour", tokens_needed=1, rate=0.0, capacity=5,
        )
        assert allowed is False

    def test_persistence_called_even_on_denial(
        self, service: RateLimitService, bucket_repository: InMemoryBucketRepository,
    ) -> None:
        bucket_repository.seed("user:1:hour", tokens=0)
        service.check_and_consume(
            "user:1:hour", tokens_needed=1, rate=0.0, capacity=5,
        )
        # Bucket state still updated (last_refill bumped).
        assert bucket_repository.write_count == 1
