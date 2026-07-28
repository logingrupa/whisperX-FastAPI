"""Unit tests for the model-residency registry.

No GPU required: loaders return sentinel objects, get_settings is
monkeypatched, and gc/empty_cache are stubbed to no-ops.
"""

import threading
from types import SimpleNamespace

import pytest
import torch

from app.infrastructure.ml import model_registry


def _fake_settings(
    enabled: bool = True, max_models: int = 8, idle_ttl: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        whisper=SimpleNamespace(
            MODEL_CACHE_ENABLED=enabled,
            MODEL_CACHE_MAX_MODELS=max_models,
            MODEL_CACHE_IDLE_TTL_SECONDS=idle_ttl,
        )
    )


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """Reset registry state + stub GPU/gc calls around every test."""
    monkeypatch.setattr(model_registry.gc, "collect", lambda: 0)
    monkeypatch.setattr(model_registry.torch.cuda, "empty_cache", lambda: None)
    monkeypatch.setattr(model_registry, "get_settings", _fake_settings)
    model_registry.evict_all("test setup")
    yield
    model_registry.evict_all("test teardown")


class _CountingLoader:
    """Loader test double: counts calls, returns fresh sentinels."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        return object()


class TestHitMiss:
    def test_miss_then_hit_loads_exactly_once(self):
        loader = _CountingLoader()
        key = ("whisper", "large-v3")

        with model_registry.lease(key, loader) as first:
            pass
        with model_registry.lease(key, loader) as second:
            pass

        assert loader.calls == 1
        assert first is second
        assert model_registry.stats()["count"] == 1

    def test_distinct_keys_get_distinct_entries(self):
        loader_a = _CountingLoader()
        loader_b = _CountingLoader()

        with model_registry.lease(("align", "lv"), loader_a) as model_a:
            pass
        with model_registry.lease(("align", "en"), loader_b) as model_b:
            pass

        assert loader_a.calls == 1
        assert loader_b.calls == 1
        assert model_a is not model_b
        assert model_registry.stats()["count"] == 2


class TestBypass:
    def test_disabled_cache_loads_every_lease_and_registry_stays_empty(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            model_registry, "get_settings", lambda: _fake_settings(enabled=False)
        )
        loader = _CountingLoader()
        key = ("whisper", "large-v3")

        with model_registry.lease(key, loader):
            pass
        with model_registry.lease(key, loader):
            pass

        assert loader.calls == 2
        assert model_registry.stats() == {"count": 0, "keys": []}


class TestConcurrency:
    def test_two_threads_cold_key_load_exactly_once(self):
        loader_started = threading.Event()
        release_loader = threading.Event()
        calls = []

        def slow_loader() -> object:
            calls.append(1)
            loader_started.set()
            release_loader.wait(timeout=5)
            return object()

        key = ("whisper", "cold")
        results = []

        def worker() -> None:
            with model_registry.lease(key, slow_loader) as model:
                results.append(model)

        thread_a = threading.Thread(target=worker)
        thread_b = threading.Thread(target=worker)
        thread_a.start()
        thread_b.start()
        assert loader_started.wait(timeout=5)
        release_loader.set()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)

        assert len(calls) == 1
        assert len(results) == 2
        assert results[0] is results[1]

    def test_independent_locks_key2_not_blocked_by_key1_holder(self):
        key1_held = threading.Event()
        release_key1 = threading.Event()
        key2_done = threading.Event()

        def hold_key1() -> None:
            with model_registry.lease(("whisper", "k1"), _CountingLoader()):
                key1_held.set()
                release_key1.wait(timeout=5)

        def lease_key2() -> None:
            with model_registry.lease(("whisper", "k2"), _CountingLoader()):
                key2_done.set()

        thread_a = threading.Thread(target=hold_key1)
        thread_a.start()
        assert key1_held.wait(timeout=5)

        thread_b = threading.Thread(target=lease_key2)
        thread_b.start()
        # key2 lease must complete WHILE key1's lock is still held.
        assert key2_done.wait(timeout=5)

        release_key1.set()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)


class TestEviction:
    def test_torch_oom_evicts_all_and_returns_true(self):
        with model_registry.lease(("whisper", "x"), _CountingLoader()):
            pass
        assert model_registry.stats()["count"] == 1

        assert model_registry.evict_on_cuda_error(torch.cuda.OutOfMemoryError()) is True
        assert model_registry.stats()["count"] == 0

    def test_runtime_cuda_text_evicts_and_returns_true(self):
        with model_registry.lease(("whisper", "x"), _CountingLoader()):
            pass

        exc = RuntimeError("CUDA error: device-side assert triggered")
        assert model_registry.evict_on_cuda_error(exc) is True
        assert model_registry.stats()["count"] == 0

    def test_runtime_oom_text_evicts_and_returns_true(self):
        exc = RuntimeError("failed to allocate: out of memory")
        assert model_registry.evict_on_cuda_error(exc) is True

    def test_app_error_keeps_cache_and_returns_false(self):
        with model_registry.lease(("whisper", "x"), _CountingLoader()):
            pass

        assert model_registry.evict_on_cuda_error(ValueError("bad audio")) is False
        assert model_registry.stats()["count"] == 1

    def test_non_cuda_runtime_error_keeps_cache(self):
        with model_registry.lease(("whisper", "x"), _CountingLoader()):
            pass

        exc = RuntimeError("tensor shape mismatch")
        assert model_registry.evict_on_cuda_error(exc) is False
        assert model_registry.stats()["count"] == 1


class TestLoaderFailure:
    def test_failed_loader_not_cached_next_lease_retries(self):
        attempts = []

        def flaky_loader() -> object:
            attempts.append(1)
            if len(attempts) == 1:
                raise OSError("model file missing")
            return object()

        key = ("whisper", "flaky")

        with pytest.raises(OSError):
            with model_registry.lease(key, flaky_loader):
                pass  # pragma: no cover — loader raises before yield

        assert model_registry.stats()["count"] == 0

        with model_registry.lease(key, flaky_loader) as model:
            assert model is not None

        assert len(attempts) == 2
        assert model_registry.stats()["count"] == 1


class TestCountCap:
    def test_cap_evicts_oldest_entry(self, monkeypatch):
        monkeypatch.setattr(
            model_registry, "get_settings", lambda: _fake_settings(max_models=2)
        )

        with model_registry.lease(("whisper", "oldest"), _CountingLoader()):
            pass
        with model_registry.lease(("whisper", "middle"), _CountingLoader()):
            pass
        with model_registry.lease(("whisper", "newest"), _CountingLoader()):
            pass

        snapshot = model_registry.stats()
        assert snapshot["count"] == 2
        assert ("whisper", "oldest") not in snapshot["keys"]
        assert ("whisper", "middle") in snapshot["keys"]
        assert ("whisper", "newest") in snapshot["keys"]


class TestIdleTtl:
    def test_idle_entry_evicted(self):
        key = ("whisper", "idle")
        with model_registry.lease(key, _CountingLoader()):
            pass
        model_registry._registry[key].last_used_at -= 999

        evicted = model_registry._sweep_idle_once(ttl_seconds=100)

        assert evicted == [key]
        assert model_registry.stats()["count"] == 0

    def test_fresh_entry_kept(self):
        key = ("whisper", "fresh")
        with model_registry.lease(key, _CountingLoader()):
            pass

        assert model_registry._sweep_idle_once(ttl_seconds=100) == []
        assert model_registry.stats()["count"] == 1

    def test_busy_entry_never_evicted(self):
        key = ("whisper", "busy")
        entry_held = threading.Event()
        release_entry = threading.Event()

        def hold_lease() -> None:
            with model_registry.lease(key, _CountingLoader()):
                model_registry._registry[key].last_used_at -= 999
                entry_held.set()
                release_entry.wait(timeout=5)

        holder = threading.Thread(target=hold_lease)
        holder.start()
        assert entry_held.wait(timeout=5)

        # Sweep runs WHILE inference lock held — entry must survive.
        assert model_registry._sweep_idle_once(ttl_seconds=100) == []
        assert model_registry.stats()["count"] == 1

        release_entry.set()
        holder.join(timeout=5)

    def test_lease_release_resets_idle_clock(self):
        key = ("whisper", "reused")
        with model_registry.lease(key, _CountingLoader()):
            pass
        model_registry._registry[key].last_used_at -= 999

        # Re-lease refreshes last_used_at — entry no longer idle.
        with model_registry.lease(key, _CountingLoader()):
            pass

        assert model_registry._sweep_idle_once(ttl_seconds=100) == []
        assert model_registry.stats()["count"] == 1

    def test_evicted_key_reloads_on_next_lease(self):
        key = ("whisper", "comeback")
        loader = _CountingLoader()
        with model_registry.lease(key, loader):
            pass
        model_registry._registry[key].last_used_at -= 999
        model_registry._sweep_idle_once(ttl_seconds=100)

        with model_registry.lease(key, loader) as model:
            assert model is not None

        assert loader.calls == 2
        assert model_registry.stats()["count"] == 1


class TestOptsHash:
    def test_none_maps_to_none(self):
        assert model_registry._opts_hash(None) is None

    def test_key_order_insensitive(self):
        assert model_registry._opts_hash({"a": 1, "b": 2}) == model_registry._opts_hash(
            {"b": 2, "a": 1}
        )

    def test_different_values_differ(self):
        assert model_registry._opts_hash({"a": 1}) != model_registry._opts_hash(
            {"a": 2}
        )
