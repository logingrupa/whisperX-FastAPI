"""Single source of truth for plan-tier limits (DRY refactor target).

Centralizes the TierPolicy dataclass + FREE_POLICY + PRO_POLICY constants +
TRIAL_DAYS so both the rate-limit enforcement path (FreeTierGate) and the
read-only usage summary path (UsageQueryService) consume identical values.

Trial + team plan tiers fall through to FREE_POLICY (matches the locked
free_tier_gate._policy_for invariant — trial == free policy by design;
team is not yet differentiated and currently uses free limits).
"""

from __future__ import annotations

from dataclasses import dataclass

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


def policy_for(plan_tier: str) -> TierPolicy:
    """Map plan_tier string to TierPolicy.

    Pro tier uses PRO_POLICY; everything else (free, trial, team, unknown)
    falls through to FREE_POLICY. Matches the FreeTierGate._policy_for
    invariant verbatim (DRY single source of truth).
    """
    if plan_tier == "pro":
        return PRO_POLICY
    return FREE_POLICY
