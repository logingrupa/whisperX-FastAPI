"""Model-residency registry — keeps whisper/align/diarize models warm in VRAM.

SINGLE-PROCESS cache. If uvicorn ever gets --workers N, this registry
duplicates per process and the VRAM math breaks — do not add --workers
without revisiting this module.

SRP: model residency only. Callers hand in a cache key + a loader; the
registry decides load-vs-reuse, serializes access per entry (whisperx
pipelines mutate instance state during inference — one instance is NOT
safe for two concurrent calls), and owns eviction policy:

- Keep-all with a count cap (``MODEL_CACHE_MAX_MODELS``, oldest-first).
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
from app.core.logging import logger


@dataclass
class _Entry:
    """One resident model slot: the loaded object + its inference lock."""

    model: Any | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    loaded_at: float = 0.0


_registry: dict[tuple, _Entry] = {}
_registry_lock = threading.Lock()


def _opts_hash(options: dict[str, Any] | None) -> int | None:
    """Stable hash for dict-valued cache-key parts (asr/vad options)."""
    if options is None:
        return None
    return hash(json.dumps(options, sort_keys=True, default=str))


def _evict_oldest_locked() -> None:
    """Evict the oldest-by-loaded_at entry. Caller holds _registry_lock."""
    oldest_key = min(_registry, key=lambda k: _registry[k].loaded_at)
    del _registry[oldest_key]
    logger.warning(
        "model_cache count cap reached — evicted oldest entry key=%s", oldest_key
    )


def _get_or_create_entry(key: tuple, max_models: int) -> _Entry:
    """Get-or-create an entry under the registry lock; enforce the count cap."""
    with _registry_lock:
        entry = _registry.get(key)
        if entry is not None:
            return entry
        if len(_registry) >= max_models:
            _evict_oldest_locked()
        entry = _Entry()
        _registry[key] = entry
        return entry


@contextmanager
def lease(key: tuple, loader: Callable[[], Any]) -> Iterator[Any]:
    """Yield the resident model for ``key``, loading it on first use.

    Holds the per-entry lock for the WHOLE with-block — inference on
    whisperx pipelines mutates instance state, so the lock must span the
    call, not just the load.
    """
    settings = get_settings()

    if not settings.whisper.MODEL_CACHE_ENABLED:
        # Bypass = rollback path: load per job, destroy after (old behavior).
        model = loader()
        try:
            yield model
        finally:
            del model
            gc.collect()
            torch.cuda.empty_cache()
        return

    entry = _get_or_create_entry(key, settings.whisper.MODEL_CACHE_MAX_MODELS)

    with entry.lock:
        if entry.model is None:
            t0 = time.perf_counter()
            try:
                entry.model = loader()
            except BaseException:
                # Never cache a broken slot — drop the entry so the next
                # lease retries the loader cleanly.
                with _registry_lock:
                    _registry.pop(key, None)
                raise
            entry.loaded_at = time.time()
            logger.info(
                "model_cache MISS key=%s load_s=%.2f",
                key,
                time.perf_counter() - t0,
            )
        else:
            logger.info("model_cache HIT key=%s load_s=0.00", key)
        yield entry.model


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
