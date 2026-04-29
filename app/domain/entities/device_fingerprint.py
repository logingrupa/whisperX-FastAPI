"""Domain entity for DeviceFingerprint — insert-once audit row."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DeviceFingerprint:
    """Insert-once row capturing per-login device fingerprint (ANTI-03).

    Attributes:
        id: Primary-key id; ``None`` until persisted.
        user_id: Owning user FK.
        cookie_hash: SHA-256 hex digest of the session cookie value.
        ua_hash: SHA-256 hex digest of the User-Agent header.
        ip_subnet: IP ``/24`` (IPv4) or ``/64`` (IPv6) network string.
        device_id: Browser-supplied UUID (localStorage).
        created_at: Row creation timestamp (tz-aware UTC).
    """

    id: int | None
    user_id: int
    cookie_hash: str
    ua_hash: str
    ip_subnet: str
    device_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
