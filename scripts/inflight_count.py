"""Print the number of tasks that are neither completed nor failed.

Used by restart-backend.ps1 as the gate before stopping the server: a restart
mid-job loses the transcription and leaks the user's concurrency slot (rate=0,
so the bucket never refills on its own).

Usage: python scripts/inflight_count.py [path/to/records.db]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

IN_FLIGHT_SQL = "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('completed', 'failed')"


def main() -> int:
    default_db = Path(__file__).resolve().parent.parent / "records.db"
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_db
    if not db_path.exists():
        print(f"records.db not found: {db_path}", file=sys.stderr)
        return 2
    connection = sqlite3.connect(str(db_path), timeout=10)
    try:
        print(connection.execute(IN_FLIGHT_SQL).fetchone()[0])
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
