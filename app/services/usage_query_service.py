"""UsageQueryService — read-only view onto rate_limit_buckets + users for /api/usage.

Refill-on-read invariant (CRITICAL): rate_limit_buckets stores token state at
the LAST consume() call. This service replays the refill formula via
``app.core.rate_limit.consume(tokens_needed=0)`` before computing derived counts.
Reading raw ``tokens`` would over-count usage as elapsed time grows.

Reset-time semantics: token buckets refill continuously; ``window_resets_at``
and ``day_resets_at`` are wall-clock approximations (top-of-next-hour UTC, next
UTC midnight) chosen to match the UI copy. The user actually gets a fractional
refill at the boundary, not the full capacity. Documented divergence — see
``RESEARCH §6.2`` in the quick-task planning artifacts.

Anti-enumeration: missing-user raises ``InvalidCredentialsError`` (mapped to
HTTP 401) for parity with ``AccountService.get_account_summary``. T-15-05 mirror.

SRP: business logic only. SQL delegates to ``IRateLimitRepository.get_by_key`` +
``IUserRepository.get_by_id``; HTTP wrapping happens in the route module.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.exceptions import InvalidCredentialsError
from app.core.plan_tiers import TRIAL_DAYS, policy_for
from app.core.rate_limit import consume
from app.domain.repositories.rate_limit_repository import IRateLimitRepository
from app.domain.repositories.user_repository import IUserRepository

HOUR_BUCKET_KEY_FMT = "user:{user_id}:tx:hour"
DAY_BUCKET_KEY_FMT = "user:{user_id}:audio_min:day"


class UsageQueryService:
    """Read-only summary builder for the ``/api/usage`` route."""

    def __init__(
        self,
        user_repository: IUserRepository,
        rate_limit_repository: IRateLimitRepository,
    ) -> None:
        self._user_repository = user_repository
        self._rate_limit_repository = rate_limit_repository

    def get_summary(
        self,
        user_id: int,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return current rate-limit + trial state for ``user_id``.

        Args:
            user_id: Caller user id (route resolves via ``authenticated_user``).
            now: Reference instant for refill replay + reset-time computation.
                 Injected for deterministic testing; defaults to ``datetime.now(UTC)``.

        Returns:
            Mapping with the wire-shape of ``UsageSummaryResponse``.

        Raises:
            InvalidCredentialsError: ``user_id`` does not resolve to a row
                (anti-enumeration parity with ``AccountService``; T-15-05).
        """
        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError()
        now_utc = now if now is not None else datetime.now(timezone.utc)
        policy = policy_for(user.plan_tier)
        hour_limit = policy.max_per_hour
        daily_minutes_limit = float(policy.max_daily_seconds // 60)
        hour_count = self._count_used(
            bucket_key=HOUR_BUCKET_KEY_FMT.format(user_id=user_id),
            capacity=hour_limit,
            rate=hour_limit / 3600.0,
            now=now_utc,
        )
        daily_minutes_used = float(
            self._count_used(
                bucket_key=DAY_BUCKET_KEY_FMT.format(user_id=user_id),
                capacity=int(daily_minutes_limit),
                rate=daily_minutes_limit / 86400.0,
                now=now_utc,
            )
        )
        trial_expires_at = (
            user.trial_started_at + timedelta(days=TRIAL_DAYS)
            if user.trial_started_at is not None
            else None
        )
        return {
            "plan_tier": user.plan_tier,
            "trial_started_at": user.trial_started_at,
            "trial_expires_at": trial_expires_at,
            "hour_count": hour_count,
            "hour_limit": hour_limit,
            "daily_minutes_used": daily_minutes_used,
            "daily_minutes_limit": daily_minutes_limit,
            "window_resets_at": self._top_of_next_hour(now_utc),
            "day_resets_at": self._next_utc_midnight(now_utc),
        }

    def _count_used(
        self, *, bucket_key: str, capacity: int, rate: float, now: datetime
    ) -> int:
        """Return tokens-consumed = capacity - refilled_tokens (zero when row absent).

        Calls ``consume(..., tokens_needed=0)`` purely for its refill side-effect
        on the in-memory bucket dict — caller does NOT persist the result, so the
        rate-limit row is unchanged (read-only path).
        """
        bucket = self._rate_limit_repository.get_by_key(bucket_key)
        if bucket is None:
            return 0
        new_state, _ = consume(
            {"tokens": bucket.tokens, "last_refill": bucket.last_refill},
            tokens_needed=0,
            now=now,
            rate=rate,
            capacity=capacity,
        )
        return max(0, capacity - new_state["tokens"])

    @staticmethod
    def _top_of_next_hour(now: datetime) -> datetime:
        return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    @staticmethod
    def _next_utc_midnight(now: datetime) -> datetime:
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight + timedelta(days=1)
