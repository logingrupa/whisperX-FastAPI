"""Disposable-email domain blocklist (ANTI-04).

Loads ``data/disposable-emails.txt`` into a frozenset at module import time.
O(1) domain lookup. Refresh policy: server restart (no hot reload — the
file is bundled with the repo).

Threat model:
    - T-13-08 (email-harvest spoofing) — blocks well-known throwaway domains
      so abusers cannot create unlimited accounts to exhaust the trial pool.
    - Loader is intentionally fail-soft: if the data file is missing the
      blocklist is empty (frozenset()) so dev environments without the file
      do not crash — production guards live at config layer (Plan 13-01).
"""

from __future__ import annotations

from pathlib import Path

# Repo-root resolution — this module lives at app/core/disposable_email.py;
# .parent.parent.parent walks up app/core -> app -> repo-root.
_BLOCKLIST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "disposable-emails.txt"
)


def _load_blocklist() -> frozenset[str]:
    """Read the blocklist file once at import; lower-case + strip lines."""
    if not _BLOCKLIST_PATH.exists():
        return frozenset()
    return frozenset(
        line.strip().lower()
        for line in _BLOCKLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


DISPOSABLE_DOMAINS: frozenset[str] = _load_blocklist()


def is_disposable(email: str) -> bool:
    """Return True if the email's domain is in the blocklist (case-insensitive).

    Accepts a full ``user@domain.tld`` address; returns False for malformed
    inputs (no ``@``) so callers can rely on a safe boolean even when called
    before pydantic validation.
    """
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].strip().lower()
    return domain in DISPOSABLE_DOMAINS
