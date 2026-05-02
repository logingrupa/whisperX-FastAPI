"""Phase 17 UAT — automated walkthrough of OPS-03/04/05 deliverables.

Sandboxed: separate port (18000), separate DB (.uat/whisperx_uat.db), separate .env.
Does NOT touch records.db or the running laragon environment.

Run from repo root:
    .venv/Scripts/python.exe scripts/uat_phase_17.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def clean(text: str) -> str:
    return ANSI_RE.sub("", text).strip().replace("\n", " | ")

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
UAT_DIR = REPO_ROOT / ".uat"
SANDBOX_DB = UAT_DIR / "whisperx_uat.db"
SANDBOX_ENV = UAT_DIR / ".env.uat"
PORT = 18000
BASE_URL = f"http://127.0.0.1:{PORT}"


@dataclass
class Result:
    track: str
    name: str
    passed: bool
    detail: str = ""


RESULTS: list[Result] = []


def record(track: str, name: str, passed: bool, detail: str = "") -> None:
    RESULTS.append(Result(track, name, passed, detail))
    icon = "PASS" if passed else "FAIL"
    print(f"  [{icon}] {name}" + (f"  -- {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Track A — docs/migration-v1.2.md structure
# ---------------------------------------------------------------------------


def track_docs() -> None:
    print("\n=== Track DOCS — runbook structure ===")
    runbook = REPO_ROOT / "docs" / "migration-v1.2.md"
    record("DOCS", "runbook file exists", runbook.is_file(), str(runbook))
    if not runbook.is_file():
        return

    text = runbook.read_text(encoding="utf-8")
    sections = re.findall(r"^## (\d+)\. ", text, re.MULTILINE)
    record(
        "DOCS",
        "9 numbered top-level sections present",
        len(sections) == 9,
        f"found {len(sections)}: {sections}",
    )

    required_commands = [
        "alembic stamp 0001_baseline",
        "alembic upgrade 0002_auth_schema",
        "alembic upgrade head",
        "python -m app.cli create-admin",
        "python -m app.cli backfill-tasks",
        "alembic downgrade -1",
    ]
    for cmd in required_commands:
        record("DOCS", f"command present: '{cmd}'", cmd in text)


# ---------------------------------------------------------------------------
# Track B — .env.example var-prefix regression
# ---------------------------------------------------------------------------


def track_env() -> None:
    print("\n=== Track ENV — .env.example vs app/core/config.py ===")
    env_file = REPO_ROOT / ".env.example"
    config_file = REPO_ROOT / "app" / "core" / "config.py"

    record("ENV", ".env.example exists", env_file.is_file())
    record("ENV", "app/core/config.py exists", config_file.is_file())
    if not (env_file.is_file() and config_file.is_file()):
        return

    env_text = env_file.read_text(encoding="utf-8")
    config_text = config_file.read_text(encoding="utf-8")

    auth_vars = sorted(set(re.findall(r"^AUTH__([A-Z0-9_]+)=", env_text, re.MULTILINE)))
    record("ENV", "Auth (v1.2) vars use AUTH__ prefix", len(auth_vars) >= 9, f"found {len(auth_vars)}")

    missing = [v for v in auth_vars if v not in config_text]
    record(
        "ENV",
        "every AUTH__* var has matching field in config.py",
        not missing,
        f"missing: {missing}" if missing else "all matched",
    )

    expected_present = [
        "AUTH__JWT_SECRET=",
        "AUTH__CSRF_SECRET=",
        "AUTH__V2_ENABLED=",
        "AUTH__COOKIE_SECURE=",
        "AUTH__FRONTEND_URL=",
        "AUTH__ARGON2_T_COST=",
        "AUTH__ARGON2_M_COST=",
        "AUTH__HCAPTCHA_ENABLED=",
    ]
    for line in expected_present:
        record("ENV", f"declares {line}", line in env_text)

    record("ENV", "secret placeholder present", "<change-me-in-production>" in env_text)
    record("ENV", "openssl generator hint present", "openssl rand -hex 32" in env_text)
    record("ENV", "cross-link to runbook present", "docs/migration-v1.2.md" in env_text)

    # DRY: zero migration command bodies in .env.example
    for cmd in ["alembic stamp 0001_baseline", "python -m app.cli backfill-tasks"]:
        record("ENV", f"DRY: '{cmd}' NOT duplicated in .env.example", cmd not in env_text)


# ---------------------------------------------------------------------------
# Track C — README structure
# ---------------------------------------------------------------------------


def track_readme() -> None:
    print("\n=== Track README — auth section structure ===")
    readme = REPO_ROOT / "README.md"
    record("README", "README.md exists", readme.is_file())
    if not readme.is_file():
        return

    text = readme.read_text(encoding="utf-8")
    required_headings = [
        "## Authentication & API Keys (v1.2)",
        "### Registration & Login Flow",
        "### Issuing API Keys",
        "### Using an API Key",
        "### Free vs Pro Tiers",
        "### Migrating from v1.1",
    ]
    for heading in required_headings:
        record("README", f"heading present: '{heading}'", heading in text)

    record("README", "bearer auth example with whsk_ prefix", "Authorization: Bearer whsk_" in text)
    record("README", "mailto reset link present", "mailto:hey@logingrupa.lv" in text)
    record("README", "links to docs/migration-v1.2.md", "docs/migration-v1.2.md" in text)

    # DRY: zero migration commands or env declarations
    for forbidden in [
        "alembic stamp 0001_baseline",
        "alembic upgrade 0002_auth_schema",
        "python -m app.cli create-admin",
        "python -m app.cli backfill-tasks",
    ]:
        record("README", f"DRY: '{forbidden}' NOT in README", forbidden not in text)


# ---------------------------------------------------------------------------
# Track D — runbook execution against synthetic v1.1 sandbox
# ---------------------------------------------------------------------------


def build_v11_baseline(db_path: Path) -> int:
    """Create a synthetic v1.1 tasks-only DB. Returns inserted row count."""
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        # Schema mirrors alembic/versions/0001_baseline.py exactly so 0002 upgrade
        # creates usage_events with a valid FK reference to tasks.id (INTEGER PK).
        conn.executescript(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT,
                status TEXT,
                result TEXT,
                file_name TEXT,
                url TEXT,
                callback_url TEXT,
                audio_duration REAL,
                language TEXT,
                task_type TEXT,
                task_params TEXT,
                duration REAL,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                error TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                progress_percentage INTEGER DEFAULT 0,
                progress_stage TEXT
            );
            INSERT INTO tasks (uuid, status, file_name, language)
              VALUES ('uat-task-1', 'completed', 'a.mp3', 'en'),
                     ('uat-task-2', 'completed', 'b.mp3', 'lv'),
                     ('uat-task-3', 'completed', 'c.mp3', 'ru');
            """
        )
        conn.commit()
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, "-m", "alembic"] + args,
        cwd=str(REPO_ROOT),
        env={**os.environ, "DB_URL": db_url, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def track_migration() -> None:
    print("\n=== Track MIGRATION — runbook on synthetic v1.1 sandbox ===")
    UAT_DIR.mkdir(exist_ok=True)
    pre_count = build_v11_baseline(SANDBOX_DB)
    db_url = f"sqlite:///{SANDBOX_DB.as_posix()}"
    record("MIGRATION", "synthetic v1.1 baseline created", pre_count == 3, f"{pre_count} rows")

    # Step 3: stamp baseline
    r = run_alembic(["stamp", "0001_baseline"], db_url)
    record("MIGRATION", "step 3: alembic stamp 0001_baseline", r.returncode == 0, clean(r.stderr)[-150:] if r.returncode else "")

    # Step 4: upgrade to 0002_auth_schema
    r = run_alembic(["upgrade", "0002_auth_schema"], db_url)
    record("MIGRATION", "step 4: alembic upgrade 0002_auth_schema", r.returncode == 0, clean(r.stderr)[-150:] if r.returncode else "")

    # Verify users table exists, tasks.user_id exists nullable
    conn = sqlite3.connect(str(SANDBOX_DB))
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        record("MIGRATION", "users table created", "users" in tables)
        record("MIGRATION", "api_keys table created", "api_keys" in tables)
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(tasks)")}
        has_user_id = "user_id" in cols
        record("MIGRATION", "tasks.user_id added (nullable)", has_user_id and cols["user_id"][3] == 0)
    finally:
        conn.close()

    # Step 5: create admin user via CLI
    admin_email = "uat-admin@example.com"
    r = subprocess.run(
        [
            PYTHON, "-c",
            "import getpass; getpass.getpass = lambda *a, **k: 'UATadminPass!1'; "
            "import app.cli; app.cli.app(['create-admin', '--email', " + repr(admin_email) + "])"
        ],
        cwd=str(REPO_ROOT),
        env={**os.environ, "DB_URL": db_url, "AUTH__JWT_SECRET": "x" * 64, "AUTH__CSRF_SECRET": "y" * 64, "PYTHONIOENCODING": "utf-8"},
        capture_output=True, text=True, encoding="utf-8",
    )
    admin_created = r.returncode == 0 and "admin" in (r.stdout + r.stderr).lower()
    record("MIGRATION", "step 5: create-admin via CLI", admin_created, clean(r.stdout + r.stderr)[-150:])

    # Step 6: backfill tasks
    r = subprocess.run(
        [
            PYTHON, "-m", "app.cli", "backfill-tasks",
            "--admin-email", admin_email, "--yes",
        ],
        cwd=str(REPO_ROOT),
        env={**os.environ, "DB_URL": db_url, "AUTH__JWT_SECRET": "x" * 64, "AUTH__CSRF_SECRET": "y" * 64, "PYTHONIOENCODING": "utf-8"},
        capture_output=True, text=True, encoding="utf-8",
    )
    record("MIGRATION", "step 6: backfill-tasks", r.returncode == 0, clean(r.stdout + r.stderr)[-150:])

    # Pre-flight guard test: revert one task to NULL and try upgrade head — must fail
    conn = sqlite3.connect(str(SANDBOX_DB))
    try:
        # First check: all rows have user_id after backfill
        orphans = conn.execute("SELECT COUNT(*) FROM tasks WHERE user_id IS NULL").fetchone()[0]
        record("MIGRATION", "all tasks assigned a user_id", orphans == 0, f"{orphans} orphans")

        # Reintroduce one orphan to test 0003 pre-flight guard
        conn.execute("UPDATE tasks SET user_id = NULL WHERE uuid = 'uat-task-1'")
        conn.commit()
    finally:
        conn.close()

    r = run_alembic(["upgrade", "head"], db_url)
    record(
        "MIGRATION",
        "pre-flight guard rejects orphan rows on upgrade head",
        r.returncode != 0 and "user_id is null" in (r.stdout + r.stderr).lower(),
        "guard fired" if r.returncode != 0 else "guard MISSED — DANGER",
    )

    # Re-fix orphan and try upgrade head again
    conn = sqlite3.connect(str(SANDBOX_DB))
    try:
        admin_id = conn.execute("SELECT id FROM users WHERE email=?", (admin_email,)).fetchone()
        if admin_id:
            conn.execute("UPDATE tasks SET user_id = ? WHERE user_id IS NULL", (admin_id[0],))
            conn.commit()
    finally:
        conn.close()

    r = run_alembic(["upgrade", "head"], db_url)
    record("MIGRATION", "step 7: alembic upgrade head succeeds after backfill", r.returncode == 0)

    # Step 8 smoke: row count parity, NOT NULL constraint
    conn = sqlite3.connect(str(SANDBOX_DB))
    try:
        post_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        record("MIGRATION", "step 8.1: row count parity", post_count == pre_count, f"pre={pre_count} post={post_count}")
        nulls = conn.execute("SELECT COUNT(*) FROM tasks WHERE user_id IS NULL").fetchone()[0]
        record("MIGRATION", "step 8.2: zero null user_id", nulls == 0)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Track E — HTTP smoke (boot uvicorn on sandbox port + DB)
# ---------------------------------------------------------------------------


def write_sandbox_env() -> None:
    UAT_DIR.mkdir(exist_ok=True)
    SANDBOX_ENV.write_text(
        "\n".join(
            [
                f"DB_URL=sqlite:///{SANDBOX_DB.as_posix()}",
                "ENVIRONMENT=development",
                "DEV=true",
                "AUTH__V2_ENABLED=true",
                "AUTH__JWT_SECRET=" + ("x" * 64),
                "AUTH__CSRF_SECRET=" + ("y" * 64),
                "AUTH__COOKIE_SECURE=false",
                "AUTH__FRONTEND_URL=http://127.0.0.1:5173",
                "AUTH__TRUST_CF_HEADER=false",
                "AUTH__HCAPTCHA_ENABLED=false",
                "LOG_LEVEL=WARNING",
                "FILTER_WARNING=true",
                "WHISPER_MODEL=tiny",
                "DEFAULT_LANG=en",
                "DEVICE=cpu",
                "COMPUTE_TYPE=int8",
            ]
        ),
        encoding="utf-8",
    )


def boot_app() -> subprocess.Popen[bytes]:
    write_sandbox_env()
    env = {
        **os.environ,
        "DB_URL": f"sqlite:///{SANDBOX_DB.as_posix()}",
        "AUTH__V2_ENABLED": "true",
        "AUTH__JWT_SECRET": "x" * 64,
        "AUTH__CSRF_SECRET": "y" * 64,
        "AUTH__COOKIE_SECURE": "false",
        "AUTH__FRONTEND_URL": "http://127.0.0.1:5173",
        "ENVIRONMENT": "development",
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT), "--no-access-log"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def wait_for_app(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


def http_call(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes, dict[str, str]]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        resp_headers = dict(resp.headers)
        body_bytes = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        resp_headers = dict(e.headers) if e.headers else {}
        body_bytes = e.read()

    set_cookies: dict[str, str] = {}
    for hk, hv in resp_headers.items():
        if hk.lower() == "set-cookie":
            for chunk in re.split(r",(?=[^;]+=)", hv):
                m = re.match(r"\s*([^=]+)=([^;]+)", chunk)
                if m:
                    set_cookies[m.group(1).strip()] = m.group(2).strip()
    return status, resp_headers, body_bytes, set_cookies


def track_http() -> None:
    print("\n=== Track HTTP — sandbox app boot + curl chain ===")
    proc = boot_app()
    try:
        ready = wait_for_app(timeout=180.0)
        record("HTTP", "uvicorn boots on sandbox env", ready, f"port={PORT} db={SANDBOX_DB.name}")
        if not ready:
            # Kill proc first so .communicate() returns instead of blocking on a long-running uvicorn.
            try:
                proc.terminate()
                stdout_bytes, _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_bytes, _ = proc.communicate(timeout=5)
            except Exception:
                stdout_bytes = b""
            tail = stdout_bytes[-2000:].decode("utf-8", errors="replace") if stdout_bytes else ""
            print(f"  boot output (last 2000 bytes):\n{tail}")
            if "libtorio_ffmpeg" in tail or "FileNotFoundError" in tail:
                print("  >>> Likely cause: torch/torchaudio FFmpeg DLLs missing in this venv.")
                print("  >>> Phase 17 docs/env/migration tests still passed; HTTP track requires a working ML stack.")
            return

        # 1. Register
        status, _, body, jar = http_call(
            "POST",
            "/auth/register",
            body={"email": "uat-alice@example.com", "password": "CorrectHorse-Battery-Staple-9"},
        )
        record("HTTP", "POST /auth/register returns 201", status == 201, f"status={status} body={body[:120]!r}")
        session = jar.get("session")
        csrf = jar.get("csrf_token")
        record("HTTP", "register sets session cookie", bool(session))
        record("HTTP", "register sets csrf_token cookie", bool(csrf))

        if session and csrf:
            # 2. Issue API key
            status, _, body, _ = http_call(
                "POST",
                "/api/keys",
                body={"name": "uat-laptop"},
                headers={"X-CSRF-Token": csrf},
                cookies={"session": session, "csrf_token": csrf},
            )
            record("HTTP", "POST /api/keys returns 201", status == 201, f"status={status}")
            try:
                key_resp = json.loads(body.decode("utf-8"))
            except Exception:
                key_resp = {}
            api_key = key_resp.get("key", "")
            record("HTTP", "issued key starts with whsk_", api_key.startswith("whsk_"), f"key={api_key[:16]}...")

            # 3. List keys
            status, _, body, _ = http_call(
                "GET",
                "/api/keys",
                cookies={"session": session, "csrf_token": csrf},
            )
            try:
                keys = json.loads(body.decode("utf-8"))
            except Exception:
                keys = []
            record("HTTP", "GET /api/keys returns list with 1 key", status == 200 and isinstance(keys, list) and len(keys) == 1)

            # 4. Anti-enumeration: missing-id and foreign-id both return 404 with same body
            status_unknown, _, body_unknown, _ = http_call(
                "DELETE", "/api/keys/99999",
                headers={"X-CSRF-Token": csrf},
                cookies={"session": session, "csrf_token": csrf},
            )
            record("HTTP", "DELETE /api/keys/<unknown> returns 404", status_unknown == 404)

            # 5. Bearer auth on a protected endpoint
            if api_key:
                status, _, body, _ = http_call("GET", "/task/", headers={"Authorization": f"Bearer {api_key}"})
                record("HTTP", "bearer auth accepted (status != 401)", status != 401, f"status={status}")

            # 6. Missing CSRF on state-mutating call returns 403
            status, _, body, _ = http_call(
                "POST",
                "/api/keys",
                body={"name": "no-csrf"},
                cookies={"session": session, "csrf_token": csrf},
            )
            record("HTTP", "POST without X-CSRF-Token returns 403", status == 403, f"status={status}")

        # 7. Logout idempotent (204)
        status, _, _, _ = http_call("POST", "/auth/logout")
        record("HTTP", "POST /auth/logout returns 204", status == 204)

        # 8. Health check
        status, _, _, _ = http_call("GET", "/health")
        record("HTTP", "GET /health returns 200", status == 200)
    finally:
        try:
            if proc.poll() is None:
                if sys.platform == "win32":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_summary() -> int:
    print("\n" + "=" * 70)
    print(" UAT RESULTS")
    print("=" * 70)
    by_track: dict[str, list[Result]] = {}
    for r in RESULTS:
        by_track.setdefault(r.track, []).append(r)
    failures = 0
    for track, items in by_track.items():
        passed = sum(1 for r in items if r.passed)
        total = len(items)
        marker = "OK" if passed == total else "FAIL"
        print(f" [{marker}] {track:<10}  {passed}/{total}")
        for r in items:
            if not r.passed:
                failures += 1
                print(f"        - FAIL: {r.name}  -- {r.detail}")
    print("=" * 70)
    print(f" Total: {len(RESULTS) - failures}/{len(RESULTS)} passed.  Failures: {failures}")
    print("=" * 70)
    return 0 if failures == 0 else 1


def cleanup() -> None:
    if UAT_DIR.exists():
        try:
            shutil.rmtree(UAT_DIR)
        except Exception:
            pass


def main() -> int:
    print("Phase 17 UAT — sandboxed walkthrough")
    print(f"  repo:    {REPO_ROOT}")
    print(f"  python:  {PYTHON}")
    print(f"  port:    {PORT}")
    print(f"  db:      {SANDBOX_DB}")
    print()

    track_docs()
    track_env()
    track_readme()
    track_migration()
    track_http()
    rc = print_summary()
    cleanup()
    return rc


if __name__ == "__main__":
    sys.exit(main())
