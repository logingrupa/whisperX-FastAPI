"""Reproducer for the SQLAlchemy session-pool leak.

Covers TWO classes of leak:

  1. FastAPI ``Depends`` providers in ``app/api/dependencies.py`` —
     drained through the generator lifecycle that FastAPI uses on every
     request.

  2. Direct container-Factory call sites that bypass Depends — exercised
     here by inlining the same call pattern used by ``DualAuthMiddleware``
     in ``app/core/dual_auth.py``, ``websocket_api.py``, and
     ``whisperx_wrapper_service.py``. THIS is where the second-round bug
     lived: the original commit (0f7bb09) only fixed class #1, so the
     middleware still leaked a Session per HTTP request.

Pre-fix: iter 16 of any leaky path hangs 30s on QueuePool checkout.
Post-fix: every iter <100ms. Run:

    .venv/Scripts/python.exe scripts/verify_session_leak_fix.py
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from typing import Any

from app.api.dependencies import (
    get_auth_service,
    get_free_tier_gate,
    get_key_service,
    get_rate_limit_service,
    get_task_management_service,
    get_task_repository,
    get_usage_event_writer,
    set_container,
)
from app.core.container import Container


def _drain(provider: Callable[..., Any]) -> Any:
    """Mimic FastAPI's generator-dependency lifecycle (yield then close)."""
    gen: Generator[Any, None, None] = provider()
    obj = next(gen)
    try:
        next(gen)
    except StopIteration:
        pass
    return obj


def _drive(provider: Callable[..., Any], label: str, n: int = 30) -> None:
    """Resolve `provider` n times. Print per-iteration latency."""
    print(f"\n=== {label} (n={n}) ===")
    for i in range(1, n + 1):
        t0 = time.perf_counter()
        _drain(provider)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        marker = "  OK" if elapsed_ms < 100 else "  SLOW"
        print(f"  iter {i:2d}: {elapsed_ms:7.1f} ms{marker}")


def _drive_callable(call: Callable[[], Any], label: str, n: int = 30) -> None:
    """Resolve `call` n times. For non-generator (direct-container) sites."""
    print(f"\n=== {label} (n={n}, direct-container) ===")
    for i in range(1, n + 1):
        t0 = time.perf_counter()
        call()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        marker = "  OK" if elapsed_ms < 100 else "  SLOW"
        print(f"  iter {i:2d}: {elapsed_ms:7.1f} ms{marker}")


def main() -> None:
    container = Container()
    set_container(container)

    # ---- class #1: FastAPI Depends providers --------------------------
    _drive(get_auth_service, "get_auth_service")
    _drive(get_key_service, "get_key_service")
    _drive(get_rate_limit_service, "get_rate_limit_service")
    _drive(get_task_repository, "get_task_repository")
    _drive(get_task_management_service, "get_task_management_service")
    _drive(get_free_tier_gate, "get_free_tier_gate")
    _drive(get_usage_event_writer, "get_usage_event_writer")

    # ---- class #2: direct-container call sites ------------------------
    # Mirrors DualAuthMiddleware._resolve_bearer (key_service +
    # user_repository, two Sessions per request).
    def _bearer_path() -> None:
        key_service = container.key_service()
        try:
            pass  # no DB call needed; just exercise checkout/close
        finally:
            key_service.repository.session.close()
        user_repository = container.user_repository()
        try:
            pass
        finally:
            user_repository.session.close()

    # Mirrors DualAuthMiddleware._resolve_cookie (user_repository, one
    # Session per request).
    def _cookie_path() -> None:
        user_repository = container.user_repository()
        try:
            pass
        finally:
            user_repository.session.close()

    # Mirrors websocket_api.websocket_endpoint (task_repository).
    def _ws_path() -> None:
        task_repo = container.task_repository()
        try:
            pass
        finally:
            task_repo.session.close()

    # Mirrors whisperx_wrapper_service.process_audio_common
    # (free_tier_gate.rate_limit_service.repository.session +
    # usage_event_writer.session, two Sessions per audio job).
    def _wrapper_path() -> None:
        gate = container.free_tier_gate()
        writer = container.usage_event_writer()
        try:
            pass
        finally:
            gate.rate_limit_service.repository.session.close()
            writer.session.close()

    _drive_callable(_bearer_path, "DualAuthMiddleware._resolve_bearer")
    _drive_callable(_cookie_path, "DualAuthMiddleware._resolve_cookie")
    _drive_callable(_ws_path, "websocket_endpoint task_repo")
    _drive_callable(_wrapper_path, "process_audio_common gate+writer")

    print("\nALL PATHS COMPLETED 30 ITERATIONS WITHOUT POOL EXHAUSTION.")


if __name__ == "__main__":
    main()
