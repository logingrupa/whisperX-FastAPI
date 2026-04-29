"""Unit tests for app.core.rate_limit (pure token bucket math).

Per .planning/phases/11-auth-core-modules-services-di/11-02-PLAN.md (Task 2 §G).
Pure-logic — no DB, no clock side-effects (now passed in).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core import rate_limit


@pytest.mark.unit
class TestRateLimit:
    def test_consume_within_budget_returns_allowed_true(self) -> None:
        now = datetime.now(timezone.utc)
        bucket: rate_limit.BucketState = {"tokens": 5, "last_refill": now}
        new_bucket, allowed = rate_limit.consume(
            bucket, tokens_needed=1, now=now, rate=0.0, capacity=10,
        )
        assert allowed is True
        assert new_bucket["tokens"] == 4

    def test_consume_over_budget_returns_allowed_false(self) -> None:
        now = datetime.now(timezone.utc)
        bucket: rate_limit.BucketState = {"tokens": 1, "last_refill": now}
        new_bucket, allowed = rate_limit.consume(
            bucket, tokens_needed=10, now=now, rate=0.0, capacity=10,
        )
        assert allowed is False
        assert new_bucket["tokens"] == 1  # unchanged on rejection

    def test_refill_caps_at_capacity(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(seconds=1000)
        bucket: rate_limit.BucketState = {"tokens": 0, "last_refill": past}
        new_bucket, allowed = rate_limit.consume(
            bucket, tokens_needed=1, now=datetime.now(timezone.utc),
            rate=1.0, capacity=10,
        )
        assert allowed is True
        assert new_bucket["tokens"] == 9  # 10 capacity - 1 consumed

    def test_clock_skew_negative_elapsed_treated_as_zero(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        bucket: rate_limit.BucketState = {"tokens": 5, "last_refill": future}
        new_bucket, allowed = rate_limit.consume(
            bucket, tokens_needed=1, now=datetime.now(timezone.utc),
            rate=10.0, capacity=10,
        )
        # Negative elapsed treated as 0 — no time-travel refill, just consume.
        assert allowed is True
        assert new_bucket["tokens"] == 4

    def test_consume_zero_tokens_always_allowed(self) -> None:
        now = datetime.now(timezone.utc)
        bucket: rate_limit.BucketState = {"tokens": 0, "last_refill": now}
        new_bucket, allowed = rate_limit.consume(
            bucket, tokens_needed=0, now=now, rate=0.0, capacity=10,
        )
        assert allowed is True
