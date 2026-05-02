"""Reproducer for the SQLAlchemy session-pool leak.

Mirrors the user's diagnostic harness AND exercises the full FastAPI
dependency lifecycle (generator drain) for every leaky provider in
app/api/dependencies.py. Pre-fix: iteration 16 hangs 30s on QueuePool
checkout. Post-fix: all 30 iterations complete in <100ms each.

Run: uv run python scripts/verify_session_leak_fix.py
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


def main() -> None:
    container = Container()
    set_container(container)

    # Each of these previously leaked. Pre-fix: iter 16 = 30000 ms.
    # Post-fix: every iter <100 ms (pool capacity 15 reused cleanly).
    _drive(get_auth_service, "get_auth_service")
    _drive(get_key_service, "get_key_service")
    _drive(get_rate_limit_service, "get_rate_limit_service")
    _drive(get_task_repository, "get_task_repository")
    _drive(get_task_management_service, "get_task_management_service")
    _drive(get_free_tier_gate, "get_free_tier_gate")
    _drive(get_usage_event_writer, "get_usage_event_writer")

    print("\nALL PROVIDERS COMPLETED 30 ITERATIONS WITHOUT POOL EXHAUSTION.")


if __name__ == "__main__":
    main()
