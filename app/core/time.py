"""Shared datetime normalisation helpers.

SQLite stores ``DATETIME`` columns without tzinfo, so values read back are
tz-naive even though the rest of the stack treats every timestamp as
tz-aware UTC. Mixing the two raises ``TypeError`` on subtraction/comparison
and serialises to ISO-8601 strings with no timezone designator (which the
frontend Zod ``.datetime({ offset: true })`` contract then rejects).

Single source of truth for the "assume persisted naive datetimes are UTC"
rule — used by ORM mappers and any service that compares persisted
timestamps against ``datetime.now(timezone.utc)``.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current instant as a tz-aware UTC datetime.

    Single source of truth for "now" across the stack. Bare ``datetime.now()``
    returns tz-naive *local* time; persisting that alongside UTC columns makes
    ``ensure_utc_aware`` stamp a local wall-clock as UTC, silently shifting the
    value by the machine's offset. Never call ``datetime.now()`` without a tz.
    """
    return datetime.now(timezone.utc)


def ensure_utc_aware(value: datetime | None) -> datetime | None:
    """Return ``value`` as a tz-aware UTC datetime; ``None`` passes through.

    A tz-naive input is assumed to already be UTC (SQLite round-trip) and is
    stamped with ``timezone.utc``. A tz-aware input is returned unchanged.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
