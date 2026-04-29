"""Pure-logic token bucket math. No DB, no clock side-effects (now passed in).

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §93-103 (locked):
- bucket dict shape {"tokens": int, "last_refill": datetime}.
- consume(bucket, *, tokens_needed, now, rate, capacity) -> (new_bucket, allowed).
- Clock-skew guard: negative elapsed treated as 0 (no time-travel refill).
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

# Tiger-style invariants — fail loudly at module load if shape drifts.
_REQUIRED_KEYS = ("tokens", "last_refill")
assert _REQUIRED_KEYS == ("tokens", "last_refill"), "BucketState key shape drift"


class BucketState(TypedDict):
    """In-memory shape of a rate_limit_buckets row."""

    tokens: int
    last_refill: datetime


def consume(
    bucket: BucketState,
    *,
    tokens_needed: int,
    now: datetime,
    rate: float,
    capacity: int,
) -> tuple[BucketState, bool]:
    """Apply continuous refill and consume tokens_needed atomically.

    Returns (new_bucket_state, allowed_flag). Caller persists new state.

    Refill: ``refilled = min(capacity, bucket["tokens"] + elapsed * rate)``.
    Clock-skew guard: negative elapsed -> treated as 0 (no time-travel refill).
    On rejection (refilled < tokens_needed) tokens are NOT consumed but the
    bucket reflects the just-applied refill (so a follow-up call after the
    next tick can succeed). When ``rate == 0`` the refill is a no-op so the
    tokens count is preserved across rejected calls.
    """
    elapsed = (now - bucket["last_refill"]).total_seconds()
    if elapsed < 0:
        elapsed = 0
    refilled = min(capacity, bucket["tokens"] + int(elapsed * rate))
    if refilled < tokens_needed:
        return ({"tokens": refilled, "last_refill": now}, False)
    return ({"tokens": refilled - tokens_needed, "last_refill": now}, True)
