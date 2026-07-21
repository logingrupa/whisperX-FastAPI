"""Guard: no tz-naive ``datetime.now()`` anywhere under ``app/``.

A bare ``datetime.now()`` returns *local* wall-clock with no tzinfo. Persisted
into a column the rest of the stack treats as UTC, ``ensure_utc_aware`` then
stamps it ``tzinfo=utc`` — so the value is not merely wrong, it is confidently
mislabelled and reads as a task that started hours in the past.

That is exactly the bug where a worker overwrote the API's correct UTC
``tasks.start_time`` with local time. Use ``app.core.time.utc_now()`` instead.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# datetime.now() with no argument, and the deprecated datetime.utcnow()
# (naive despite the name).
NAIVE_NOW_PATTERN = re.compile(r"datetime\.(now\(\s*\)|utcnow\(\s*\))")

# Prose, not code: comments and reStructuredText ``literals`` inside docstrings
# legitimately name the forbidden call while explaining why it is forbidden.
PROSE_PATTERN = re.compile(r"^\s*#|``")


def test_app_has_no_naive_datetime_now() -> None:
    assert APP_ROOT.is_dir(), f"app root not found: {APP_ROOT}"

    offenders: list[str] = []
    for source_file in APP_ROOT.rglob("*.py"):
        for line_number, line in enumerate(
            source_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if PROSE_PATTERN.search(line):
                continue
            if NAIVE_NOW_PATTERN.search(line):
                relative_path = source_file.relative_to(APP_ROOT.parent)
                offenders.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert not offenders, (
        "tz-naive datetime.now()/utcnow() found — use app.core.time.utc_now():\n"
        + "\n".join(offenders)
    )
