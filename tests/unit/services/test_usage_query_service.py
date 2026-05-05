"""Unit tests for UsageQueryService (quick-260505-l2w).

Coverage:
  - DTO shape (all required keys present)
  - bucket-absent fallback (zero counts)
  - refill-on-read (consume(tokens_needed=0) replays refill before counting)
  - pro tier limits sourced via plan_tiers.policy_for
  - trial tier limits identical to free
  - trial_expires_at = trial_started_at + 7d (None when started_at None)
  - InvalidCredentialsError on user-not-found (anti-enumeration parity)
  - now injected as kwarg (deterministic boundaries)
  - window_resets_at = top-of-next-hour UTC
  - day_resets_at = next UTC midnight
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import InvalidCredentialsError
from app.core.plan_tiers import FREE_POLICY, PRO_POLICY
from app.domain.entities.rate_limit_bucket import RateLimitBucket
from app.domain.entities.user import User
from app.services.usage_query_service import UsageQueryService


# Fixed reference instant — middle of an hour, mid-day UTC, deterministic boundaries.
_NOW = datetime(2026, 5, 5, 14, 30, 45, tzinfo=timezone.utc)


def _make_user(
    *,
    user_id: int = 42,
    plan_tier: str = "trial",
    trial_started_at: datetime | None = None,
) -> User:
    return User(
        id=user_id,
        email=f"u{user_id}@x.com",
        password_hash="x",
        plan_tier=plan_tier,
        trial_started_at=trial_started_at,
    )


class _StubUserRepo:
    def __init__(self, user: User | None) -> None:
        self._user = user
        self.calls: list[int] = []

    def get_by_id(self, identifier: int) -> User | None:
        self.calls.append(identifier)
        return self._user


class _StubRateLimitRepo:
    """Returns canned RateLimitBucket per bucket_key; None if absent."""

    def __init__(self, buckets: dict[str, RateLimitBucket] | None = None) -> None:
        self._buckets = buckets or {}
        self.lookup_calls: list[str] = []

    def get_by_key(self, bucket_key: str) -> RateLimitBucket | None:
        self.lookup_calls.append(bucket_key)
        return self._buckets.get(bucket_key)

    def upsert_atomic(
        self, bucket_key: str, new_state: dict[str, Any]
    ) -> None:  # pragma: no cover — read-only path
        raise AssertionError("UsageQueryService must NOT write to rate-limit store")


def _make_service(user: User | None, buckets: dict[str, RateLimitBucket] | None = None) -> UsageQueryService:
    return UsageQueryService(
        user_repository=_StubUserRepo(user),
        rate_limit_repository=_StubRateLimitRepo(buckets),
    )


# ---------------------------------------------------------------------------
# DTO shape + happy-path fallback
# ---------------------------------------------------------------------------


def test_get_summary_returns_required_keys_for_trial_user_with_no_buckets() -> None:
    user = _make_user(plan_tier="trial", trial_started_at=_NOW - timedelta(days=2))
    service = _make_service(user)

    summary = service.get_summary(user_id=42, now=_NOW)

    expected_keys = {
        "plan_tier",
        "trial_started_at",
        "trial_expires_at",
        "hour_count",
        "hour_limit",
        "daily_minutes_used",
        "daily_minutes_limit",
        "window_resets_at",
        "day_resets_at",
    }
    assert set(summary.keys()) == expected_keys
    assert summary["plan_tier"] == "trial"
    assert summary["hour_count"] == 0
    assert summary["daily_minutes_used"] == 0.0
    assert summary["hour_limit"] == FREE_POLICY.max_per_hour
    assert summary["daily_minutes_limit"] == float(FREE_POLICY.max_daily_seconds // 60)


# ---------------------------------------------------------------------------
# Refill-on-read invariant
# ---------------------------------------------------------------------------


def test_get_summary_applies_refill_on_read_for_hour_bucket() -> None:
    user = _make_user(plan_tier="free")
    # Bucket with last_refill == now and tokens=2 -> no time elapsed, refill is a no-op.
    # hour_count = capacity(5) - tokens(2) = 3.
    buckets = {
        "user:42:tx:hour": RateLimitBucket(
            id=1, bucket_key="user:42:tx:hour", tokens=2, last_refill=_NOW
        ),
    }
    service = _make_service(user, buckets)

    summary = service.get_summary(user_id=42, now=_NOW)

    assert summary["hour_count"] == 3


def test_get_summary_applies_refill_on_read_for_daily_bucket() -> None:
    user = _make_user(plan_tier="free")
    # Daily capacity is 30 minutes; tokens=10, last_refill=now -> daily_minutes_used = 30 - 10 = 20.
    buckets = {
        "user:42:audio_min:day": RateLimitBucket(
            id=2, bucket_key="user:42:audio_min:day", tokens=10, last_refill=_NOW
        ),
    }
    service = _make_service(user, buckets)

    summary = service.get_summary(user_id=42, now=_NOW)

    assert summary["daily_minutes_used"] == 20.0


def test_get_summary_refill_on_read_replays_elapsed_time() -> None:
    """Tokens stale on read MUST be refilled before counting (CRITICAL)."""
    user = _make_user(plan_tier="free")
    # last_refill 1 hour ago, tokens=0 -> free hour cap=5, rate=5/3600 -> after 1h refilled to 5.
    # hour_count = 5 - 5 = 0 (full bucket means caller used nothing recently).
    one_hour_ago = _NOW - timedelta(hours=1)
    buckets = {
        "user:42:tx:hour": RateLimitBucket(
            id=1, bucket_key="user:42:tx:hour", tokens=0, last_refill=one_hour_ago
        ),
    }
    service = _make_service(user, buckets)

    summary = service.get_summary(user_id=42, now=_NOW)

    assert summary["hour_count"] == 0


# ---------------------------------------------------------------------------
# Plan-tier limits via plan_tiers.policy_for
# ---------------------------------------------------------------------------


def test_get_summary_pro_user_uses_pro_policy_limits() -> None:
    user = _make_user(plan_tier="pro")
    service = _make_service(user)

    summary = service.get_summary(user_id=42, now=_NOW)

    assert summary["hour_limit"] == PRO_POLICY.max_per_hour
    assert summary["daily_minutes_limit"] == float(PRO_POLICY.max_daily_seconds // 60)


def test_get_summary_trial_user_uses_free_policy_limits() -> None:
    user = _make_user(plan_tier="trial")
    service = _make_service(user)

    summary = service.get_summary(user_id=42, now=_NOW)

    assert summary["hour_limit"] == FREE_POLICY.max_per_hour
    assert summary["daily_minutes_limit"] == float(FREE_POLICY.max_daily_seconds // 60)


# ---------------------------------------------------------------------------
# Trial-state derivation
# ---------------------------------------------------------------------------


def test_get_summary_trial_expires_at_is_started_plus_7_days() -> None:
    started = _NOW - timedelta(days=3)
    user = _make_user(plan_tier="trial", trial_started_at=started)
    service = _make_service(user)

    summary = service.get_summary(user_id=42, now=_NOW)

    assert summary["trial_started_at"] == started
    assert summary["trial_expires_at"] == started + timedelta(days=7)


def test_get_summary_trial_expires_at_none_when_started_at_none() -> None:
    user = _make_user(plan_tier="free", trial_started_at=None)
    service = _make_service(user)

    summary = service.get_summary(user_id=42, now=_NOW)

    assert summary["trial_started_at"] is None
    assert summary["trial_expires_at"] is None


# ---------------------------------------------------------------------------
# Anti-enumeration: missing user
# ---------------------------------------------------------------------------


def test_get_summary_missing_user_raises_invalid_credentials() -> None:
    service = _make_service(user=None)

    with pytest.raises(InvalidCredentialsError):
        service.get_summary(user_id=999, now=_NOW)


# ---------------------------------------------------------------------------
# Reset-time semantics (wall-clock approximations)
# ---------------------------------------------------------------------------


def test_get_summary_window_resets_at_is_top_of_next_hour() -> None:
    user = _make_user(plan_tier="trial")
    service = _make_service(user)

    summary = service.get_summary(user_id=42, now=_NOW)

    # _NOW is 14:30:45 UTC -> top-of-next-hour = 15:00:00 UTC.
    assert summary["window_resets_at"] == datetime(
        2026, 5, 5, 15, 0, 0, tzinfo=timezone.utc
    )


def test_get_summary_day_resets_at_is_next_utc_midnight() -> None:
    user = _make_user(plan_tier="trial")
    service = _make_service(user)

    summary = service.get_summary(user_id=42, now=_NOW)

    # _NOW is 2026-05-05 14:30 UTC -> next midnight = 2026-05-06 00:00 UTC.
    assert summary["day_resets_at"] == datetime(
        2026, 5, 6, 0, 0, 0, tzinfo=timezone.utc
    )


# ---------------------------------------------------------------------------
# Read-only invariant: service must NOT write to rate-limit store
# ---------------------------------------------------------------------------


def test_get_summary_does_not_write_to_rate_limit_store() -> None:
    user = _make_user(plan_tier="trial")
    rate_limit_repo = _StubRateLimitRepo({})
    service = UsageQueryService(
        user_repository=_StubUserRepo(user),
        rate_limit_repository=rate_limit_repo,
    )

    # Stub raises AssertionError if upsert_atomic is called -> if we get here, no writes.
    service.get_summary(user_id=42, now=_NOW)
    assert "user:42:tx:hour" in rate_limit_repo.lookup_calls
    assert "user:42:audio_min:day" in rate_limit_repo.lookup_calls
