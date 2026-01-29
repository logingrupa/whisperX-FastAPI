"""Cleanup scheduler for expired TUS upload sessions.

Runs a periodic background job to remove incomplete uploads that have
passed their expiry time, preventing disk space from filling up with
abandoned upload sessions.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tuspyserver.file import gc_files
from tuspyserver.router import TusRouterOptions

from app.core.logging import logger
from app.api.tus_upload_api import TUS_UPLOAD_DIR

CLEANUP_INTERVAL_MINUTES: int = 10
"""Interval between cleanup runs in minutes (per BACK-06 requirement)."""

scheduler: AsyncIOScheduler = AsyncIOScheduler()


def _build_gc_options() -> TusRouterOptions:
    """Build a minimal TusRouterOptions for gc_files cleanup.

    Returns:
        TusRouterOptions configured with the TUS upload directory and
        default expiry settings.
    """
    return TusRouterOptions(
        prefix="files",
        files_dir=str(TUS_UPLOAD_DIR),
        max_size=0,
        auth=None,
        days_to_keep=1,
        on_upload_complete=None,
        upload_complete_dep=None,
        pre_create_hook=None,
        pre_create_dep=None,
        file_dep=None,
        tags=None,
        tus_version="1.0.0",
        tus_extension="",
        strict_offset_validation=False,
    )


def cleanup_expired_uploads() -> None:
    """Remove expired TUS upload files from the upload directory.

    Calls tuspyserver's gc_files to find and delete uploads whose
    expiry timestamp has passed. Errors are logged but never propagated
    to avoid crashing the scheduler.
    """
    try:
        options = _build_gc_options()
        gc_files(options)
        logger.info("Cleanup completed for expired TUS upload sessions")
    except FileNotFoundError:
        logger.debug(
            "TUS upload directory does not exist yet; skipping cleanup"
        )
    except Exception:
        logger.exception("Error during TUS upload cleanup")


def start_cleanup_scheduler() -> None:
    """Start the background cleanup scheduler.

    Adds an interval job that runs cleanup_expired_uploads every
    CLEANUP_INTERVAL_MINUTES minutes, runs an immediate cleanup on
    startup, and starts the APScheduler event loop.
    """
    scheduler.add_job(
        cleanup_expired_uploads,
        trigger="interval",
        minutes=CLEANUP_INTERVAL_MINUTES,
        id="cleanup_expired_uploads",
        replace_existing=True,
    )
    cleanup_expired_uploads()
    scheduler.start()
    logger.info(
        "Started upload cleanup scheduler (interval: %d min)",
        CLEANUP_INTERVAL_MINUTES,
    )


def stop_cleanup_scheduler() -> None:
    """Stop the background cleanup scheduler.

    Shuts down APScheduler without waiting for running jobs to complete.
    """
    scheduler.shutdown(wait=False)
    logger.info("Stopped upload cleanup scheduler")
