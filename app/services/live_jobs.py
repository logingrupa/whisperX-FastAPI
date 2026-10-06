"""Identifiers of jobs that have a live worker in this process.

A 'processing' row whose identifier is missing here has no worker: it was
never queued, or its worker ended without writing a terminal status (for
example a "database is locked" on the final update). Resubmit dedupe must not
hand such a row back. The server is one process and the startup sweep fails
every 'processing' row at boot, so this set and the database agree on which
rows are alive.

A submit marks its job live before the INSERT, so a concurrent identical
submit never sees the new row as dead; the worker's ``finally`` removes it.
"""

import threading

_live_identifiers: set[str] = set()
_lock = threading.Lock()


def mark_live(identifier: str) -> None:
    """Record that ``identifier`` has (or is about to have) a worker."""
    if not identifier:
        raise ValueError("Job identifier must be non-empty")
    with _lock:
        _live_identifiers.add(identifier)


def mark_finished(identifier: str) -> None:
    """Forget ``identifier``; a no-op if it was never marked."""
    with _lock:
        _live_identifiers.discard(identifier)


def is_live(identifier: str) -> bool:
    """True while ``identifier`` has a queued or running worker."""
    with _lock:
        return identifier in _live_identifiers
