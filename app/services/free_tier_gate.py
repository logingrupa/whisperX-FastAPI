"""FreeTierGate — enforces RATE-03..RATE-10 in fail-fast order.

Per Phase 13 CONTEXT §137-145 (locked):

  Free policy:  hourly cap + file duration + daily cap + tiny/small models, no diarize, 1 concurrent
  Pro policy:   hourly cap + 60min file + 600min/day, all models, diarize OK, 3 concurrent
  Trial policy: identical to free; expires at trial_started_at + 7 days -> 402

Plan-tier limit values live in ``app.core.plan_tiers`` (single source of
truth, DRY) — do NOT hardcode magic numbers here; both this gate and the
read-only UsageQueryService consume the same module.

Concurrency slot lifecycle (W1 fix):
  - check() consumes 1 token from `user:{id}:concurrent` (capacity=max_concurrent, rate=0)
  - process_audio_common's completion hook calls release_concurrency(user) in
    try/finally so the slot is ALWAYS refunded (success OR failure).

SRP: gating only. Persistence + bucket math live in RateLimitService.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.exceptions import (
    ConcurrencyLimitError,
    FreeTierViolationError,
    RateLimitExceededError,
    TrialExpiredError,
)
from app.core.plan_tiers import (
    FREE_POLICY,
    PRO_POLICY,
    TRIAL_DAYS,
    TierPolicy,
    policy_for,
)
from app.domain.entities.user import User
from app.services.auth.rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)

# Re-export DRY-imported names so legacy callers that still
# `from app.services.free_tier_gate import FREE_POLICY` keep working.
__all__ = [
    "FreeTierGate",
    "FREE_POLICY",
    "PRO_POLICY",
    "TRIAL_DAYS",
    "TierPolicy",
    "concurrency_bucket_key",
]


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
        return policy_for(user.plan_tier)

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
          - trial expiry              -> TrialExpiredError (402)
          - hourly transcribe rate    -> RateLimitExceededError (429 + Retry-After)
          - file duration             -> FreeTierViolationError (403)
          - allowed model             -> FreeTierViolationError (403)
          - diarization allowed       -> FreeTierViolationError (403)
          - daily audio min cap       -> RateLimitExceededError (429 + Retry-After)
          - concurrency slot acquired -> ConcurrencyLimitError (429 + Retry-After)
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
