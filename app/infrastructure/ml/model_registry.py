"""Model-residency registry — keeps whisper/align/diarize models warm in VRAM.

SINGLE-PROCESS cache. If uvicorn ever gets --workers N, this registry
duplicates per process and the VRAM math breaks — do not add --workers
without revisiting this module.

SRP: model residency only. Callers hand in a cache key + a loader; the
registry decides load-vs-reuse, serializes access per entry (whisperx
pipelines mutate instance state during inference — one instance is NOT
safe for two concurrent calls), and owns eviction policy:

- Keep-all with a count cap (``MODEL_CACHE_MAX_MODELS``, oldest-first).
- Idle TTL (``MODEL_CACHE_IDLE_TTL_SECONDS``, 0 = keep forever): a
  background sweeper evicts entries unused longer than the TTL, freeing
  VRAM between jobs. Entries mid-inference are never evicted.
- Evict ALL on CUDA errors (context may be corrupted — self-healing back
  to cold-load behavior).
- Keep cache on app errors (model state untouched).
- ``MODEL_CACHE_ENABLED=false`` bypasses entirely: load-per-job +
  destroy-after, byte-for-byte the pre-cache behavior (rollback path).
"""

import gc
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import torch

from app.core.config import get_settings
from app.core.gpu_lock import gpu_slot
from app.core.logging import logger


@dataclass
class _Entry:
    """One resident model slot: the loaded object + its inference lock."""

    model: Any | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    loaded_at: float = 0.0
    last_used_at: float = 0.0


_registry: dict[tuple, _Entry] = {}
_registry_lock = threading.Lock()


def _opts_hash(options: dict[str, Any] | None) -> int | None:
    """Stable hash for dict-valued cache-key parts (asr/vad options)."""
    if options is None:
        return None
    return hash(json.dumps(options, sort_keys=True, default=str))


def _evict_oldest_locked() -> bool:
    """Evict the oldest loaded, idle entry. Caller holds _registry_lock.

    Entries still loading or mid-inference are skipped; when every entry is
    busy the registry runs over the cap until a later lease finds one idle.
    Returns whether an entry was evicted.
    """
    idle_keys = [
        key
        for key, entry in _registry.items()
        if entry.model is not None and not entry.lock.locked()
    ]
    if not idle_keys:
        logger.warning("model_cache count cap reached but every entry is busy; over cap for now")
        return False
    oldest_key = min(idle_keys, key=lambda k: _registry[k].loaded_at)
    del _registry[oldest_key]
    logger.warning(
        "model_cache count cap reached — evicted oldest entry key=%s", oldest_key
    )
    return True


def _slot_holder(key: tuple) -> str:
    """GPU-slot log label for a cache key: kind + model, e.g. ``whisper/large-v3``."""
    return "/".join(str(part) for part in key[:2])


def _get_or_create_entry(key: tuple, max_models: int) -> _Entry:
    """Get-or-create an entry under the registry lock; enforce the count cap.

    Touches ``last_used_at`` under the SAME lock the idle sweeper holds, so
    an entry handed to a caller cannot be idle-evicted before the caller
    acquires its inference lock.
    """
    with _registry_lock:
        entry = _registry.get(key)
        if entry is None:
            # Trim back to the cap, which a busy period may have overrun.
            while len(_registry) >= max_models and _evict_oldest_locked():
                pass
            entry = _Entry()
            _registry[key] = entry
        entry.last_used_at = time.time()
        return entry


def _acquire_live_entry(key: tuple, max_models: int) -> _Entry:
    """Lock the entry the registry currently holds for ``key``.

    An entry can be evicted (evict-all, count cap) while a caller waits on
    its lock; running on it then would use an orphaned model. Retry until
    the locked entry is still the registered one. Lock order: entry lock,
    then _registry_lock (the sweeper only try-locks entries).
    """
    while True:
        entry = _get_or_create_entry(key, max_models)
        entry.lock.acquire()
        with _registry_lock:
            if _registry.get(key) is entry:
                return entry
        entry.lock.release()


@contextmanager
def lease(key: tuple, loader: Callable[[], Any]) -> Iterator[Any]:
    """Yield the resident model for ``key``, loading it on first use.

    Holds the per-entry lock for the WHOLE with-block — inference on
    whisperx pipelines mutates instance state, so the lock must span the
    call, not just the load.

    The GPU slot is taken AFTER the entry lock: a job queued behind another
    job on the same model waits without holding a slot that a job on a
    different model could use.
    """
    settings = get_settings()

    if not settings.whisper.MODEL_CACHE_ENABLED:
        # Bypass = rollback path: load per job, destroy after (old behavior).
        with gpu_slot(_slot_holder(key)):
            model = loader()
            try:
                yield model
            finally:
                del model
                gc.collect()
                torch.cuda.empty_cache()
        return

    if settings.whisper.MODEL_CACHE_IDLE_TTL_SECONDS > 0:
        _ensure_sweeper()

    entry = _acquire_live_entry(key, settings.whisper.MODEL_CACHE_MAX_MODELS)
    try:
        with gpu_slot(_slot_holder(key)):
            if entry.model is None:
                _load_into(entry, key, loader)
            else:
                logger.info("model_cache HIT key=%s load_s=0.00", key)
            try:
                yield entry.model
            finally:
                # Idle clock counts from job END, not start — a long job must
                # not expire its own model.
                entry.last_used_at = time.time()
    finally:
        entry.lock.release()


def _load_into(entry: _Entry, key: tuple, loader: Callable[[], Any]) -> None:
    """Load the model into a locked entry; a failed load drops this entry."""
    t0 = time.perf_counter()
    try:
        entry.model = loader()
    except BaseException:
        # Never cache a broken slot — drop THIS entry (not a newer one that
        # replaced it) so the next lease retries the loader cleanly.
        with _registry_lock:
            if _registry.get(key) is entry:
                del _registry[key]
        raise
    entry.loaded_at = time.time()
    logger.info(
        "model_cache MISS key=%s load_s=%.2f",
        key,
        time.perf_counter() - t0,
    )


_SWEEP_INTERVAL_SECONDS = 60.0
_sweeper_start_lock = threading.Lock()
_sweeper_thread: threading.Thread | None = None


def _sweep_idle_once(ttl_seconds: float) -> list[tuple]:
    """Evict entries unused for longer than ``ttl_seconds``.

    Entries whose inference lock is held are skipped (never evict a model
    mid-job) — non-blocking acquire, retried on the next sweep.
    """
    now = time.time()
    evicted: list[tuple] = []
    with _registry_lock:
        for key in list(_registry):
            entry = _registry[key]
            if now - entry.last_used_at < ttl_seconds:
                continue
            if not entry.lock.acquire(blocking=False):
                continue
            try:
                del _registry[key]
                entry.model = None
                evicted.append(key)
            finally:
                entry.lock.release()
    if evicted:
        gc.collect()
        torch.cuda.empty_cache()
        logger.info(
            "model_cache IDLE-EVICT ttl_s=%.0f evicted_keys=%s",
            ttl_seconds,
            evicted,
        )
    return evicted


def _sweeper_loop() -> None:
    while True:
        time.sleep(_SWEEP_INTERVAL_SECONDS)
        ttl_seconds = get_settings().whisper.MODEL_CACHE_IDLE_TTL_SECONDS
        if ttl_seconds > 0:
            _sweep_idle_once(ttl_seconds)


def _ensure_sweeper() -> None:
    """Start the idle-sweeper daemon thread once per process."""
    global _sweeper_thread
    if _sweeper_thread is not None:
        return
    with _sweeper_start_lock:
        if _sweeper_thread is not None:
            return
        _sweeper_thread = threading.Thread(
            target=_sweeper_loop, name="model-cache-idle-sweeper", daemon=True
        )
        _sweeper_thread.start()


def evict_all(reason: str) -> None:
    """Drop every resident model and release VRAM. Loud by design."""
    with _registry_lock:
        evicted_keys = list(_registry.keys())
        _registry.clear()
    gc.collect()
    torch.cuda.empty_cache()
    logger.warning(
        "model_cache EVICT-ALL reason=%s evicted_keys=%s", reason, evicted_keys
    )


def evict_on_cuda_error(exc: BaseException) -> bool:
    """Evict everything if ``exc`` is a CUDA-class failure.

    Subtype-first: torch's typed OOM, then RuntimeError text matching —
    ctranslate2 surfaces OOM as plain RuntimeError text. App errors
    (ValidationError, KeyError, bad audio, ...) return False: cache kept.
    """
    if not _is_cuda_error(exc):
        return False
    evict_all(f"cuda_error: {exc}")
    return True


def _is_cuda_error(exc: BaseException) -> bool:
    if isinstance(exc, torch.cuda.OutOfMemoryError):
        return True
    if not isinstance(exc, RuntimeError):
        return False
    message = str(exc).lower()
    return "out of memory" in message or "cuda" in message


def stats() -> dict[str, Any]:
    """Snapshot for logging/tests: resident entry count + keys."""
    with _registry_lock:
        return {"count": len(_registry), "keys": list(_registry.keys())}
