"""Reap tasks left in ``processing`` by a previous process.

Transcription runs in FastAPI ``BackgroundTasks``, i.e. in-process worker
threads. When the process dies — restart, crash, power loss — every in-flight
task loses its worker but keeps ``status='processing'`` in the database
forever. Nothing ever finishes or fails it.

Those rows are corrosive out of proportion to their number: the dashboard shows
work that is not happening, ``processing`` counts read as a queue backlog that
does not exist, and an operator diagnosing a "stuck queue" chases a worker that
exited hours ago. On 2026-07-21 exactly that cost a long debugging detour.

Because workers cannot outlive the process, any ``processing`` row observed at
startup is orphaned by definition. That makes the sweep unconditional and safe:
no age threshold to tune, and no window in which it could kill a live job.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.core.time import utc_now

_ORPHAN_ERROR = (
    "Orphaned: the worker process exited while this task was still running "
    "(service restart or crash). Marked failed at startup; resubmit to retry."
)


def reap_orphaned_tasks(session: Session) -> int:
    """Mark every ``processing`` task as ``failed``. Returns the number swept.

    Call once during application startup, before any new work is accepted.

    Args:
        session: Database session to run the sweep in.

    Returns:
        Count of rows transitioned from ``processing`` to ``failed``.
    """
    now = utc_now()
    result = session.execute(
        text(
            "UPDATE tasks SET status = 'failed', error = :error, "
            "end_time = :now, updated_at = :now "
            "WHERE status = 'processing'"
        ),
        {"error": _ORPHAN_ERROR, "now": now},
    )
    session.commit()

    swept = int(result.rowcount or 0)
    if swept:
        logger.warning(
            "Startup sweep: marked %d orphaned task(s) as failed "
            "(worker died with a previous process)",
            swept,
        )
    else:
        logger.info("Startup sweep: no orphaned tasks")
    return swept
