"""CI benchmark: 100 Argon2id hashes p99 < 300ms (VERIFY-05).

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §210 (locked):
gated behind the slow pytest marker — not part of default `pytest` run.
Invoke explicitly: `pytest -m slow tests/integration/test_argon2_benchmark.py`.
"""

from __future__ import annotations

import time

import pytest

from app.core import password_hasher

_ITERATIONS = 100
_BUDGET_MS = 300.0


@pytest.mark.slow
@pytest.mark.integration
class TestArgon2Benchmark:
    """Benchmark gate (VERIFY-05): p99 latency under 300ms over 100 hashes."""

    def test_argon2_p99_under_300ms(self) -> None:
        durations_ms: list[float] = []
        for i in range(_ITERATIONS):
            t0 = time.perf_counter()
            password_hasher.hash(f"benchmark-pwd-{i}")
            durations_ms.append((time.perf_counter() - t0) * 1000.0)
        durations_ms.sort()
        # Index 98 of 100 sorted = p99 (the 99th-percentile value).
        p99 = durations_ms[_ITERATIONS - 2]
        assert p99 < _BUDGET_MS, (
            f"Argon2 p99={p99:.1f}ms exceeded {_BUDGET_MS:.0f}ms budget "
            f"(min={durations_ms[0]:.1f}, max={durations_ms[-1]:.1f}, "
            f"median={durations_ms[_ITERATIONS // 2]:.1f})"
        )
