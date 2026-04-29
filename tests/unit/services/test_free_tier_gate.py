"""Unit tests for FreeTierGate (Phase 13-08, RATE-01..12 + BILL-01).

Coverage (≥11):
  1.  test_free_user_under_quota_passes
  2.  test_free_user_at_5_per_hour_raises_rate_limit
  3.  test_free_user_file_too_long_raises
  4.  test_free_user_model_not_allowed_raises
  5.  test_free_user_diarize_disabled_raises
  6.  test_pro_user_higher_limits
  7.  test_trial_expired_raises
  8.  test_trial_not_started_passes_for_first_use
  9.  test_daily_audio_cap_consumes
  10. test_concurrency_limit_enforced
  11. test_concurrency_slot_released_after_completion (W1)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import (
    ConcurrencyLimitError,
    FreeTierViolationError,
    RateLimitExceededError,
    TrialExpiredError,
)
from app.domain.entities.user import User
from app.services.free_tier_gate import (
    FREE_POLICY,
    PRO_POLICY,
    FreeTierGate,
    concurrency_bucket_key,
)


def _make_user(
    *,
    user_id: int = 1,
    plan_tier: str = "free",
    trial_started_at: datetime | None = None,
) -> User:
    return User(
        id=user_id,
        email=f"u{user_id}@x.com",
        password_hash="x",
        plan_tier=plan_tier,
        trial_started_at=trial_started_at,
    )


class _StubRateLimitService:
    """Programmable RLS stub: returns canned `allowed` per bucket key.

    `allow_map` keyed by bucket_key prefix; first matching prefix wins.
    Defaults to True if no key matches. Tracks `released` calls.
    """

    def __init__(self, allow_map: dict[str, bool] | None = None) -> None:
        self.allow_map = allow_map or {}
        self.consumed_calls: list[tuple[str, int, float, int]] = []
        self.released_calls: list[tuple[str, int, int]] = []

    def check_and_consume(
        self,
        bucket_key: str,
        *,
        tokens_needed: int,
        rate: float,
        capacity: int,
    ) -> bool:
        self.consumed_calls.append((bucket_key, tokens_needed, rate, capacity))
        for prefix, allowed in self.allow_map.items():
            if prefix in bucket_key:
                return allowed
        return True

    def release(
        self,
        bucket_key: str,
        *,
        tokens: int = 1,
        capacity: int = 1,
    ) -> None:
        self.released_calls.append((bucket_key, tokens, capacity))


@pytest.mark.unit
class TestFreeTierGate:
    def test_free_user_under_quota_passes(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        gate.check(user=user, file_seconds=120.0, model="tiny", diarize=False)
        # Bucket lookups: hour, daily, concurrent
        assert any("tx:hour" in c[0] for c in rls.consumed_calls)
        assert any("audio_min:day" in c[0] for c in rls.consumed_calls)
        assert any("concurrent" in c[0] for c in rls.consumed_calls)

    def test_free_user_at_5_per_hour_raises_rate_limit(self) -> None:
        rls = _StubRateLimitService(allow_map={"tx:hour": False})
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        with pytest.raises(RateLimitExceededError) as exc_info:
            gate.check(
                user=user, file_seconds=60.0, model="tiny", diarize=False
            )
        assert exc_info.value.details["retry_after_seconds"] == 60

    def test_free_user_file_too_long_raises(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        with pytest.raises(FreeTierViolationError) as exc_info:
            gate.check(
                user=user, file_seconds=400.0, model="tiny", diarize=False,
            )
        assert "exceeds" in str(exc_info.value).lower()

    def test_free_user_model_not_allowed_raises(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        with pytest.raises(FreeTierViolationError) as exc_info:
            gate.check(
                user=user, file_seconds=60.0, model="large-v3", diarize=False
            )
        assert "large-v3" in str(exc_info.value)

    def test_free_user_diarize_disabled_raises(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        with pytest.raises(FreeTierViolationError) as exc_info:
            gate.check(
                user=user, file_seconds=60.0, model="tiny", diarize=True
            )
        assert "diarization" in str(exc_info.value).lower()

    def test_pro_user_higher_limits(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="pro")
        # 50min file + large-v3 + diarize=True — all allowed for pro
        gate.check(
            user=user,
            file_seconds=50 * 60,
            model="large-v3",
            diarize=True,
        )
        # Verify pro hourly capacity sent to RLS
        hour_calls = [c for c in rls.consumed_calls if "tx:hour" in c[0]]
        assert hour_calls
        assert hour_calls[0][3] == PRO_POLICY.max_per_hour

    def test_trial_expired_raises(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(
            plan_tier="trial",
            trial_started_at=datetime.now(timezone.utc) - timedelta(days=8),
        )
        with pytest.raises(TrialExpiredError):
            gate.check(
                user=user, file_seconds=60.0, model="tiny", diarize=False
            )

    def test_trial_not_started_passes_for_first_use(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="trial", trial_started_at=None)
        # No raise: trial counter not started yet
        gate.check(user=user, file_seconds=60.0, model="tiny", diarize=False)

    def test_daily_audio_cap_consumes(self) -> None:
        """Daily cap fires when audio_min bucket returns False."""
        rls = _StubRateLimitService(allow_map={"audio_min:day": False})
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        with pytest.raises(RateLimitExceededError) as exc_info:
            gate.check(
                user=user,
                file_seconds=300.0,  # 5 min
                model="tiny",
                diarize=False,
            )
        assert exc_info.value.details["retry_after_seconds"] == 3600

    def test_daily_audio_cap_tokens_proportional_to_minutes(self) -> None:
        """5-minute file consumes 5 tokens from the daily bucket."""
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        gate.check(
            user=user, file_seconds=300.0, model="tiny", diarize=False
        )
        day_calls = [c for c in rls.consumed_calls if "audio_min:day" in c[0]]
        assert day_calls
        # tokens_needed should be 5 (300s/60)
        assert day_calls[0][1] == 5

    def test_concurrency_limit_enforced(self) -> None:
        """When concurrent bucket returns False -> ConcurrencyLimitError."""
        rls = _StubRateLimitService(allow_map={"concurrent": False})
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        with pytest.raises(ConcurrencyLimitError):
            gate.check(
                user=user, file_seconds=60.0, model="tiny", diarize=False
            )

    def test_concurrency_slot_released_after_completion(self) -> None:
        """W1 round-trip: acquire, release, acquire again succeeds."""
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(user_id=42, plan_tier="free")

        # Acquire (consumes 1 slot)
        gate.check(user=user, file_seconds=60.0, model="tiny", diarize=False)

        # Release: must record a release call against the right bucket
        gate.release_concurrency(user)
        assert rls.released_calls
        bucket, tokens, capacity = rls.released_calls[0]
        assert bucket == concurrency_bucket_key(42)
        assert tokens == 1
        assert capacity == FREE_POLICY.max_concurrent

    def test_release_concurrency_pro_uses_pro_capacity(self) -> None:
        """Pro release passes PRO_POLICY.max_concurrent (=3) to RLS."""
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="pro")
        gate.release_concurrency(user)
        assert rls.released_calls[0][2] == PRO_POLICY.max_concurrent

    def test_check_diarize_route_pro_passes(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="pro")
        gate.check_diarize_route(user)  # no raise

    def test_check_diarize_route_free_raises(self) -> None:
        rls = _StubRateLimitService()
        gate = FreeTierGate(rls)  # type: ignore[arg-type]
        user = _make_user(plan_tier="free")
        with pytest.raises(FreeTierViolationError):
            gate.check_diarize_route(user)

    def test_concurrency_bucket_key_is_deterministic(self) -> None:
        assert concurrency_bucket_key(7) == "user:7:concurrent"
