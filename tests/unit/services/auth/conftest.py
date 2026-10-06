"""Shared fakes for the auth-service unit tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypeVar

import pytest

from app.domain.entities.rate_limit_bucket import RateLimitBucket

T = TypeVar("T")


class InMemoryBucketRepository:
    """IRateLimitRepository fake: buckets in a dict, updates applied in place."""

    def __init__(self) -> None:
        self.buckets: dict[str, RateLimitBucket] = {}
        self.write_count = 0

    def seed(self, bucket_key: str, *, tokens: int) -> None:
        self.buckets[bucket_key] = RateLimitBucket(
            id=len(self.buckets) + 1,
            bucket_key=bucket_key,
            tokens=tokens,
            last_refill=datetime.now(timezone.utc),
        )

    def get_by_key(self, bucket_key: str) -> RateLimitBucket | None:
        return self.buckets.get(bucket_key)

    def update_atomic(
        self,
        bucket_key: str,
        compute: Callable[[RateLimitBucket | None], tuple[dict[str, Any] | None, T]],
    ) -> T:
        new_state, result = compute(self.buckets.get(bucket_key))
        if new_state is not None:
            self.write_count += 1
            self.buckets[bucket_key] = RateLimitBucket(
                id=1,
                bucket_key=bucket_key,
                tokens=new_state["tokens"],
                last_refill=new_state["last_refill"],
            )
        return result


@pytest.fixture
def bucket_repository() -> InMemoryBucketRepository:
    return InMemoryBucketRepository()
