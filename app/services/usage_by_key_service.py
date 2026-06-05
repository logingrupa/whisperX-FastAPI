"""UsageByKeyService — per-API-key usage breakdown for /api/usage/by-key.

Aggregates the historical ``usage_events`` rows for one user, grouped by the
``api_key_id`` that was attributed at transcription time (added in migration
0004). Rows with a NULL ``api_key_id`` — pre-attribution history and
cookie/session-authenticated transcriptions — collapse into a single
synthetic "unattributed" bucket (``api_key_id = None``).

SRP: read-only aggregation only. One GROUP BY query; the route module owns
HTTP wrapping and the schema owns the wire-shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.time import ensure_utc_aware


def _coerce_dt(value: Any) -> datetime | None:
    """Normalise a SQLite ``MAX(created_at)`` result to a tz-aware datetime.

    Raw ``text()`` queries bypass SQLAlchemy column processors, so SQLite
    hands back a string (e.g. ``2026-06-05 21:31:56.347564+00:00``). Parse
    it, then stamp UTC if tz-naive (shared rule) so the wire value always
    carries a timezone the frontend Zod contract accepts.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return ensure_utc_aware(value)

# LEFT JOIN so a row whose key was later deleted (FK SET NULL) or never
# attributed still surfaces — its name resolves to NULL -> "unattributed".
_BREAKDOWN_SQL = """
SELECT
    ue.api_key_id                          AS api_key_id,
    ak.name                                AS name,
    ak.prefix                              AS prefix,
    ak.revoked_at                          AS revoked_at,
    COUNT(*)                               AS transcription_count,
    COALESCE(SUM(ue.file_seconds), 0.0)    AS total_seconds,
    MAX(ue.created_at)                      AS last_used_at
FROM usage_events AS ue
LEFT JOIN api_keys AS ak ON ak.id = ue.api_key_id
WHERE ue.user_id = :user_id
GROUP BY ue.api_key_id
ORDER BY total_seconds DESC
"""


class UsageByKeyService:
    """Read-only per-API-key usage aggregator for the caller."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_breakdown(self, user_id: int) -> list[dict[str, Any]]:
        """Return one row per API key (plus an 'unattributed' bucket).

        Each row carries the wire-shape of ``UsageByKeyEntry``:
        api_key_id, name, prefix, revoked, transcription_count,
        minutes_used (1-decimal), last_used_at.
        """
        rows = self._session.execute(
            text(_BREAKDOWN_SQL), {"user_id": user_id}
        ).mappings()
        return [self._to_entry(row) for row in rows]

    @staticmethod
    def _to_entry(row: Any) -> dict[str, Any]:
        api_key_id = row["api_key_id"]
        is_attributed = api_key_id is not None
        return {
            "api_key_id": api_key_id,
            "name": row["name"] if is_attributed else None,
            "prefix": row["prefix"] if is_attributed else None,
            "revoked": is_attributed and row["revoked_at"] is not None,
            "transcription_count": int(row["transcription_count"]),
            "minutes_used": round(float(row["total_seconds"]) / 60.0, 1),
            "last_used_at": _coerce_dt(row["last_used_at"]),
        }
