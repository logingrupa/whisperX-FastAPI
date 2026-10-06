"""Global GPU execution guard — caps concurrent model work on the GPU.

One process-wide semaphore bounds how many model leases (load + inference
of one whisper / align / diarize model) run on the GPU at once. Concurrent
loads on a single GPU beyond what VRAM holds cause CUDA out-of-memory or a
driver-level stall that hangs the whole device.

``model_registry.lease`` takes the slot AFTER the model's own entry lock, so
a job waiting behind another job on the same model never holds a slot that a
job on a different model could use.

SRP: GPU admission control only (no task state, no billing). DRY: one
definition, taken in one place (``model_registry.lease``).

The billing-tier ``FreeTierGate`` concurrency slot is unrelated: it caps how
many jobs a *user* may have in flight for accounting. This lock caps how many
model leases may touch the *hardware* at once. Both are needed.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.logging import logger

# Max model leases allowed on the GPU concurrently. Default 1 = strict
# serialization. start-server-boot.bat raises it to 2 on the 24 GB card.
_MAX_CONCURRENT_GPU_JOBS = max(1, int(os.getenv("GPU_MAX_CONCURRENT_JOBS", "1")))

_gpu_semaphore = threading.Semaphore(_MAX_CONCURRENT_GPU_JOBS)


@contextmanager
def gpu_slot(holder: str) -> Iterator[None]:
    """Block until a GPU slot is free, then hold it for the whole ``with`` body.

    The slot is released on the way out even if the body raises
    (context-manager finally), so a crashed lease never wedges the GPU for
    the others.

    Args:
        holder: Log label for who holds the slot (model kind + name).
    """
    if not holder:
        raise ValueError("gpu_slot holder label must be non-empty")
    logger.debug("GPU slot: waiting (holder=%s)", holder)
    _gpu_semaphore.acquire()
    logger.info("GPU slot: acquired (holder=%s)", holder)
    try:
        yield
    finally:
        _gpu_semaphore.release()
        logger.info("GPU slot: released (holder=%s)", holder)
