"""FreeTierGate — enforces RATE-03..RATE-10 in fail-fast order.

Per Phase 13 CONTEXT §137-145 (locked):

  Free policy:  5 req/hr, 5min file, 30min/day, tiny+small models, no diarize, 1 concurrent
  Pro policy:   100 req/hr, 60min file, 600min/day, all models, diarize OK, 3 concurrent
  Trial policy: identical to free; expires at trial_started_at + 7 days -> 402

Concurrency slot lifecycle (W1 fix):
  - check() consumes 1 token from `user:{id}:concurrent` (capacity=max_concurrent, rate=0)
  - process_audio_common's completion hook calls release_concurrency(user) in
    try/finally so the slot is ALWAYS refunded (success OR failure).

SRP: gating only. Persistence + bucket math live in RateLimitService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.exceptions import (
    ConcurrencyLimitError,
    FreeTierViolationError,
    RateLimitExceededError,
    TrialExpiredError,
)
from app.domain.entities.user import User
from app.services.auth.rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)

TRIAL_DAYS = 7


@dataclass(frozen=True)
class TierPolicy:
    """Immutable per-tier policy values.

    Attributes:
        max_per_hour: Hourly transcribe cap (token bucket capacity).
        max_file_seconds: Max single-file duration in seconds.
        max_daily_seconds: Max cumulative audio per day in seconds.
        allowed_models: Whisper model names permitted on this tier.
        diarization_allowed: Whether diarize=True is allowed on this tier.
        max_concurrent: Max simultaneous transcriptions per user.
    """

    max_per_hour: int
    max_file_seconds: int
    max_daily_seconds: int
    allowed_models: frozenset[str]
    diarization_allowed: bool
    max_concurrent: int


FREE_POLICY = TierPolicy(
    max_per_hour=5,
    max_file_seconds=5 * 60,
    max_daily_seconds=30 * 60,
    allowed_models=frozenset({"tiny", "small"}),
    diarization_allowed=False,
    max_concurrent=1,
)


PRO_POLICY = TierPolicy(
    max_per_hour=100,
    max_file_seconds=60 * 60,
    max_daily_seconds=600 * 60,
    allowed_models=frozenset(
        {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}
    ),
    diarization_allowed=True,
    max_concurrent=3,
)


def concurrency_bucket_key(user_id: int) -> str:
    """Single source of truth for the concurrency slot bucket key (DRT)."""
    return f"user:{user_id}:concurrent"


class FreeTierGate:
    """Enforce free / pro / trial tier policies (CONTEXT §137-145).

    Public API:
      - check(user, file_seconds, model, diarize) — runs all 6 gates fail-fast
      - check_diarize_route(user) — pro-only diarize-route guard
      - release_concurrency(user) — refund 1 concurrency slot (W1)
    """

    def __init__(self, rate_limit_service: RateLimitService) -> None:
        self.rate_limit_service = rate_limit_service

    # ------------------------------------------------------------------
    # Policy resolution
    # ------------------------------------------------------------------

    def _policy_for(self, user: User) -> TierPolicy:
        if user.plan_tier == "pro":
            return PRO_POLICY
        return FREE_POLICY

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        *,
        user: User,
        file_seconds: float,
        model: str,
        diarize: bool,
    ) -> None:
        """Run all 6 fail-fast gates. Raises on first failure.

        Order (CONTEXT §138):
          1. trial expiry              -> TrialExpiredError (402)
          2. hourly transcribe rate    -> RateLimitExceededError (429 + Retry-After)
          3. file duration             -> FreeTierViolationError (403)
          4. allowed model             -> FreeTierViolationError (403)
          5. diarization allowed       -> FreeTierViolationError (403)
          6. daily audio min cap       -> RateLimitExceededError (429 + Retry-After)
          7. concurrency slot acquired -> ConcurrencyLimitError (429 + Retry-After)
        """
        policy = self._policy_for(user)
        user_id = int(user.id)  # type: ignore[arg-type]
        self._check_trial_expiry(user)
        self._check_hourly_rate(user_id, policy)
        self._check_file_duration(file_seconds, policy)
        self._check_model(model, policy)
        self._check_diarization(diarize, policy)
        self._check_daily_minutes(user_id, file_seconds, policy)
        self._check_concurrency(user_id, policy)

    def check_diarize_route(self, user: User) -> None:
        """Pro-only diarize-route guard (no transcribe rate hit)."""
        self._check_trial_expiry(user)
        if not self._policy_for(user).diarization_allowed:
            raise FreeTierViolationError("Diarization not available on your plan")

    def release_concurrency(self, user: User) -> None:
        """Release 1 concurrency slot for ``user``.

        Must be called from the transcription completion path in a
        try/finally so the slot is returned on BOTH success and failure
        paths (W1 — failure to release locks the user out of further
        transcribes until the bucket resets).
        """
        policy = self._policy_for(user)
        user_id = int(user.id)  # type: ignore[arg-type]
        self.rate_limit_service.release(
            concurrency_bucket_key(user_id),
            tokens=1,
            capacity=policy.max_concurrent,
        )

    # ------------------------------------------------------------------
    # Per-gate guards (SRP — one method per policy dimension)
    # ------------------------------------------------------------------

    def _check_trial_expiry(self, user: User) -> None:
        if user.plan_tier != "trial":
            return
        if user.trial_started_at is None:
            return
        now = datetime.now(timezone.utc)
        if user.trial_started_at + timedelta(days=TRIAL_DAYS) < now:
            raise TrialExpiredError()

    def _check_hourly_rate(self, user_id: int, policy: TierPolicy) -> None:
        bucket_key = f"user:{user_id}:tx:hour"
        allowed = self.rate_limit_service.check_and_consume(
            bucket_key,
            tokens_needed=1,
            rate=policy.max_per_hour / 3600.0,
            capacity=policy.max_per_hour,
        )
        if not allowed:
            raise RateLimitExceededError(
                bucket_key=bucket_key, retry_after_seconds=60
            )

    def _check_file_duration(
        self, file_seconds: float, policy: TierPolicy
    ) -> None:
        if file_seconds > policy.max_file_seconds:
            raise FreeTierViolationError(
                f"File duration {int(file_seconds)}s exceeds tier limit "
                f"{policy.max_file_seconds}s"
            )

    def _check_model(self, model: str, policy: TierPolicy) -> None:
        if model not in policy.allowed_models:
            raise FreeTierViolationError(
                f"Model '{model}' not available on your plan"
            )

    def _check_diarization(
        self, diarize: bool, policy: TierPolicy
    ) -> None:
        if diarize and not policy.diarization_allowed:
            raise FreeTierViolationError(
                "Diarization not available on your plan"
            )

    def _check_daily_minutes(
        self, user_id: int, file_seconds: float, policy: TierPolicy
    ) -> None:
        tokens_needed = max(1, int(file_seconds / 60))
        bucket_key = f"user:{user_id}:audio_min:day"
        capacity_minutes = policy.max_daily_seconds // 60
        allowed = self.rate_limit_service.check_and_consume(
            bucket_key,
            tokens_needed=tokens_needed,
            rate=capacity_minutes / 86400.0,
            capacity=capacity_minutes,
        )
        if not allowed:
            raise RateLimitExceededError(
                bucket_key=bucket_key, retry_after_seconds=3600
            )

    def _check_concurrency(self, user_id: int, policy: TierPolicy) -> None:
        # Slot held until process_audio_common completion-hook calls
        # release_concurrency(user). rate=0 -> no auto-refill; release is
        # the only path back to a full bucket (W1).
        allowed = self.rate_limit_service.check_and_consume(
            concurrency_bucket_key(user_id),
            tokens_needed=1,
            rate=0.0,
            capacity=policy.max_concurrent,
        )
        if not allowed:
            raise ConcurrencyLimitError()
