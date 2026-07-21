"""Global GPU execution guard — single-GPU serialization.

One process-wide semaphore serializes heavy GPU model work so that no two
transcription / alignment / diarization jobs load models into the same VRAM
at once. Concurrent loads on a single GPU cause CUDA out-of-memory or a
driver-level stall that hangs the whole device. Serializing to one job at a
time removes both failure modes with no real throughput loss — a single GPU
cannot run these in parallel anyway; overlap only thrashes VRAM.

SRP: GPU admission control only (no task state, no billing). DRY: one
definition imported by every GPU entry point (full pipeline + individual
services).

The billing-tier ``FreeTierGate`` concurrency slot is unrelated: it caps how
many jobs a *user* may have in flight for accounting. This lock caps how many
jobs may touch the *hardware* at once. Both are needed.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.logging import logger

# Max jobs allowed on the GPU concurrently. Default 1 = strict serialization,
# correct for a single GPU. Raise via env only for multi-GPU or large-VRAM
# hosts that can hold several model sets at once.
_MAX_CONCURRENT_GPU_JOBS = max(1, int(os.getenv("GPU_MAX_CONCURRENT_JOBS", "1")))

_gpu_semaphore = threading.Semaphore(_MAX_CONCURRENT_GPU_JOBS)


@contextmanager
def gpu_slot(identifier: str = "") -> Iterator[None]:
    """Block until a GPU slot is free, then hold it for the whole ``with`` body.

    Serializes GPU model load + inference across all BackgroundTask worker
    threads so concurrent jobs never double-load models into VRAM. The slot is
    released on the way out even if the body raises (context-manager finally),
    so a crashed job never wedges the GPU for the others.

    Args:
        identifier: Task id, for log correlation only.
    """
    logger.debug("GPU slot: waiting (task=%s)", identifier)
    _gpu_semaphore.acquire()
    logger.info("GPU slot: acquired (task=%s)", identifier)
    try:
        yield
    finally:
        _gpu_semaphore.release()
        logger.info("GPU slot: released (task=%s)", identifier)
