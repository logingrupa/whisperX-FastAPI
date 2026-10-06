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

from app.core.time import ensure_utc_aware
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



# SQL LIKE pattern matching every concurrency_bucket_key().
CONCURRENCY_BUCKET_KEY_PATTERN = "user:%:concurrent"


def hourly_bucket_key(user_id: int) -> str:
    """Bucket key for the per-user hourly transcribe count."""
    return f"user:{user_id}:tx:hour"


def daily_minutes_bucket_key(user_id: int) -> str:
    """Bucket key for the per-user daily audio-minute budget."""
    return f"user:{user_id}:audio_min:day"


def _minute_tokens(file_seconds: float) -> int:
    """Daily-bucket tokens a file costs: whole minutes, at least one."""
    return max(1, int(file_seconds / 60))


def _daily_capacity_minutes(policy: TierPolicy) -> int:
    return policy.max_daily_seconds // 60

class FreeTierGate:
    """Enforce free / pro / trial tier policies (CONTEXT §137-145).

    Public API:
      - check(user, file_seconds, model, diarize) — runs all 6 gates fail-fast
      - check_diarize_route(user) — pro-only diarize-route guard
      - check_file_duration(user, file_seconds) — tier file-length cap alone
      - check_upload_allowed(user, model) — checks that need no duration
      - reconcile_daily_minutes(user, charged, decoded) — settle the daily bucket
      - release_concurrency(user) — refund 1 concurrency slot (W1)
      - release_admission(user, file_seconds) — refund all a check() consumed
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
        unlimited: bool = False,
    ) -> None:
        """Run all 6 fail-fast gates. Raises on first failure.

        ``unlimited=True`` (set when the request authenticated via an API key
        whose per-key ``unlimited`` flag is on) bypasses EVERY gate and
        consumes NO rate-limit token / concurrency slot. The matching release
        path (``release_slot_if_authed``) likewise skips the refund for such
        a task, so the per-user concurrency bucket is left untouched and the
        user's other (limited) keys keep accounting correctly.

        Order (debug fix — quota leak): pure validators (zero-cost config
        checks) run FIRST, then rate-bucket consumers. A duration / model /
        diarize-policy rejection must NOT cost the user a slot of hourly
        quota — that bug was visible as "Hour quota 1/5 even though my
        upload was rejected".

        Failure modes:
          - trial expiry              -> TrialExpiredError (402)         [pure]
          - file duration             -> FreeTierViolationError (403)    [pure]
          - allowed model             -> FreeTierViolationError (403)    [pure]
          - diarization allowed       -> FreeTierViolationError (403)    [pure]
          - hourly transcribe rate    -> RateLimitExceededError (429)    [consumes 1 token]
          - daily audio min cap       -> RateLimitExceededError (429)    [consumes N tokens]
          - concurrency slot acquired -> ConcurrencyLimitError  (429)    [consumes 1 token, released in finally]
        """
        if unlimited:
            return
        policy = self._policy_for(user)
        user_id = int(user.id)  # type: ignore[arg-type]
        # Pure validators (no bucket consume) — fail-fast on config violations
        # before we touch any rate-limit token.
        self._check_trial_expiry(user)
        self._check_file_duration(file_seconds, policy)
        self._check_model(model, policy)
        self._check_diarization(diarize, policy)
        # Rate consumers — order matters: hourly first (smallest token),
        # daily next, concurrency last (its slot is released in finally).
        # A rejection gives back what the earlier buckets already took.
        self._check_hourly_rate(user_id, policy)
        try:
            self._check_daily_minutes(user_id, file_seconds, policy)
        except RateLimitExceededError:
            self._release_hourly_token(user_id, policy)
            raise
        try:
            self._check_concurrency(user_id, policy)
        except ConcurrencyLimitError:
            self._release_hourly_token(user_id, policy)
            self._release_daily_minutes(user_id, file_seconds, policy)
            raise

    def check_file_duration(self, user: User, file_seconds: float) -> None:
        """Re-check only the tier's file-length cap (no bucket consumed).

        For the background job once it has decoded the audio: the submit
        gated on the container's reported duration, which a truncated or
        forged header can misstate.
        """
        self._check_file_duration(file_seconds, self._policy_for(user))

    def check_upload_allowed(self, user: User, model: str) -> None:
        """Run the checks that need no file duration and consume no bucket.

        For TUS upload creation: trial expiry and model entitlement reject
        before a multi-GB upload starts. check() still runs every gate once
        the upload is complete and its duration is known.
        """
        policy = self._policy_for(user)
        self._check_trial_expiry(user)
        self._check_model(model, policy)

    def reconcile_daily_minutes(
        self, user: User, charged_seconds: float, decoded_seconds: float
    ) -> None:
        """Settle the daily audio-minute bucket once the real length is known.

        check() charged the container's reported duration. Consumes the extra
        minutes when the decoded audio is longer (RateLimitExceededError if
        the day's budget cannot cover them) and refunds the surplus when it
        is shorter.
        """
        policy = self._policy_for(user)
        user_id = int(user.id)  # type: ignore[arg-type]
        extra_tokens = _minute_tokens(decoded_seconds) - _minute_tokens(charged_seconds)
        if extra_tokens < 0:
            self.rate_limit_service.release(
                daily_minutes_bucket_key(user_id),
                tokens=-extra_tokens,
                capacity=_daily_capacity_minutes(policy),
            )
            return
        if extra_tokens > 0:
            self._consume_daily_minutes(user_id, extra_tokens, policy)

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

    def release_admission(self, user: User, file_seconds: float) -> None:
        """Refund everything check() consumed, for a submit that created no job.

        Returns the hourly token, the daily audio minutes for ``file_seconds``
        and the concurrency slot.
        """
        policy = self._policy_for(user)
        user_id = int(user.id)  # type: ignore[arg-type]
        self._release_hourly_token(user_id, policy)
        self._release_daily_minutes(user_id, file_seconds, policy)
        self.release_concurrency(user)

    def _release_hourly_token(self, user_id: int, policy: TierPolicy) -> None:
        self.rate_limit_service.release(
            hourly_bucket_key(user_id), tokens=1, capacity=policy.max_per_hour
        )

    def _release_daily_minutes(
        self, user_id: int, file_seconds: float, policy: TierPolicy
    ) -> None:
        self.rate_limit_service.release(
            daily_minutes_bucket_key(user_id),
            tokens=_minute_tokens(file_seconds),
            capacity=_daily_capacity_minutes(policy),
        )

    # ------------------------------------------------------------------
    # Per-gate guards (SRP — one method per policy dimension)
    # ------------------------------------------------------------------

    def _check_trial_expiry(self, user: User) -> None:
        if user.plan_tier != "trial":
            return
        if user.trial_started_at is None:
            return
        # SQLite returns naive datetimes for DATETIME columns; normalise to
        # tz-aware UTC (shared rule) so comparison never crashes with
        # "can't compare offset-naive and offset-aware".
        started = ensure_utc_aware(user.trial_started_at)
        now = datetime.now(timezone.utc)
        if started + timedelta(days=TRIAL_DAYS) < now:
            raise TrialExpiredError()

    def _check_hourly_rate(self, user_id: int, policy: TierPolicy) -> None:
        bucket_key = hourly_bucket_key(user_id)
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
        self._consume_daily_minutes(user_id, _minute_tokens(file_seconds), policy)

    def _consume_daily_minutes(
        self, user_id: int, tokens_needed: int, policy: TierPolicy
    ) -> None:
        bucket_key = daily_minutes_bucket_key(user_id)
        capacity_minutes = _daily_capacity_minutes(policy)
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
