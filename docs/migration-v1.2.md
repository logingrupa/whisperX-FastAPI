# Migration Runbook: v1.1 -> v1.2 (Multi-User Auth + API Keys)

Audience: operator with shell access to the host running whisperX. Scope: migrate an existing v1.1 deployment (single shared bearer token, `tasks` table only) to v1.2 (multi-user auth, API keys, billing-ready schema). Risk: irreversible schema changes — backup is mandatory. Time: ~5 minutes on a small DB; the backfill step (Section 6) scales linearly with the `tasks` row count.

Step ordering in this runbook mirrors `tests/integration/test_migration_smoke.py` 1:1 (executable proof-of-runbook). For env var configuration, see [`.env.example`](../.env.example).

---

## 1. Overview

What this migration does:

- Replaces `Base.metadata.create_all()` with Alembic migrations as the single schema source of truth.
- Adds six new tables: `users`, `api_keys`, `subscriptions`, `usage_events`, `rate_limit_buckets`, `device_fingerprints`.
- Adds `tasks.user_id` foreign key (initially nullable, then tightened to NOT NULL).
- Backfills every pre-existing `tasks` row to a newly-created admin user.
- Adds `idx_tasks_user_id` for per-user task queries.

Migration chain:

| Revision | Purpose |
|----------|---------|
| `0001_baseline` | Empty-stamp baseline matching the v1.1 `tasks` shape |
| `0002_auth_schema` | Six new auth/billing tables + nullable `tasks.user_id` |
| `0003_tasks_user_id_not_null` | Tighten `tasks.user_id` to NOT NULL + add `idx_tasks_user_id` |

Pre-requisite checklist:

- Working directory: project root (where `alembic.ini` lives).
- `uv sync` has run; `.venv` is active.
- `.env` has `DB_URL` pointing at the production records.db.
- `.env` has `AUTH__V2_ENABLED=true` (master gate; without it the v1.2 auth/keys/billing routers never mount — see [`.env.example`](../.env.example) and `app/main.py:247-252`).
- Operator has shell-level access with a real TTY (not just `docker exec` without `-it`) — `getpass` in Section 5 needs an interactive terminal.
- Application is stopped or out of rotation for the duration of the migration.

Step ordering invariants (fail-loud at each boundary):

| Invariant | Enforced by |
|-----------|-------------|
| Backup exists before any schema mutation | Section 2 (operator-driven `cp`) |
| Admin user exists before backfill runs | Section 5 precedes Section 6; `backfill-tasks` resolves admin by `--admin-email` and exits 1 if not found |
| Backfill completes before `upgrade head` | Section 6 precedes Section 7; migration `0003` pre-flight raises `RuntimeError` if any orphan rows remain |

---

## 2. Pre-flight: Backup Database

Purpose: copy the production SQLite file so Section 9 (Rollback) can restore byte-for-byte if anything fails downstream.

Stop the application or take it out of rotation, then copy the DB file. Replace `records.db` with the path your `DB_URL` points at.

```bash
cp records.db records.db.pre-v1.2.bak
```

Expected output: silent success (no output on a successful `cp`).

Verify the backup is non-empty and readable:

```bash
sqlite3 records.db.pre-v1.2.bak "SELECT COUNT(*) FROM tasks;"
```

Expected output: an integer matching the live `tasks` row count.

```bash
sqlite3 records.db.pre-v1.2.bak ".tables"
```

Expected output: `tasks` (and any v1.1 sidecar tables if present).

Failure mode: if `cp` fails or the verify queries error, STOP. Do not proceed. Investigate disk space, file lock, or path permissions before continuing.

---

## 3. Stamp Baseline (alembic stamp 0001_baseline)

Purpose: mark the existing brownfield `records.db` as already at revision `0001_baseline`. Do NOT run `alembic upgrade` from base — that would try to recreate the existing `tasks` table and fail.

Pre-flight check:

```bash
sqlite3 records.db ".tables" | grep -w tasks
```

Expected output: `tasks`. If absent, you do not have a v1.1 deployment — abort.

Run the stamp from the project root with `.venv` activated:

```bash
uv run alembic stamp 0001_baseline
```

Expected output:

```
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running stamp_revision  -> 0001_baseline
```

Verify the stamp landed:

```bash
uv run alembic current
```

Expected output: `0001_baseline (head)`.

Failure mode: `alembic_version` table missing or pointing at an unknown revision. Restore from `records.db.pre-v1.2.bak` (Section 9, option B) and retry.

---

## 4. Upgrade Auth Schema (alembic upgrade 0002_auth_schema)

Purpose: create the six auth/billing tables and add the nullable `tasks.user_id` foreign key. Existing `tasks` rows are preserved; `tasks.user_id` is `NULL` on every pre-existing row until Section 6 backfills them.

Pre-flight check (chain head must be `0001_baseline` from Section 3):

```bash
uv run alembic current
```

Expected output: `0001_baseline (head)`.

Run the upgrade:

```bash
uv run alembic upgrade 0002_auth_schema
```

Expected output:

```
INFO  [alembic.runtime.migration] Running upgrade 0001_baseline -> 0002_auth_schema, auth_schema
```

Verify the new tables exist:

```bash
sqlite3 records.db ".tables"
```

Expected output (alphabetical):

```
alembic_version      device_fingerprints  subscriptions        usage_events
api_keys             rate_limit_buckets   tasks                users
```

Verify `tasks` gained the `user_id` column (still nullable at this revision):

```bash
sqlite3 records.db "PRAGMA table_info(tasks);" | grep user_id
```

Expected output: a row matching `<ordinal>|user_id|INTEGER|0||0` (the `0` after the type indicates `NOT NULL=0`, i.e. nullable).

Failure mode: `IntegrityError` or `OperationalError` mid-upgrade. Restore from backup (Section 9, option B) and investigate before retrying.

---

## 5. Create Admin User

Purpose: create the user row that Section 6 will reassign every orphan task to. Must run BEFORE backfill — `backfill-tasks` exits 1 if `--admin-email` does not resolve.

The CLI prompts for the password TWICE via `getpass.getpass()`. The password is never echoed, never logged, and never accepted as a CLI flag (passwords as flags leak into shell history and `ps aux`).

Replace the email with a real operator address:

```bash
uv run python -m app.cli create-admin --email admin@example.com
```

Expected interaction:

```
Admin password: <type, no echo>
Confirm password: <type, no echo>
Admin user 1 created with email admin@example.com
```

Exit code: 0 on success. Exit 1 on password mismatch, duplicate email, weak password, or any `ValidationError`.

Verify the admin row landed with `plan_tier='pro'`:

```bash
sqlite3 records.db "SELECT id, email, plan_tier FROM users WHERE email='admin@example.com';"
```

Expected output: `1|admin@example.com|pro`.

> **Windows / non-TTY note:** `getpass.getpass()` requires a real terminal. Piping the password via `echo "pw\npw" |` does NOT work on Windows (`msvcrt.getwch()` reads keyboard directly). Run this command in an interactive shell. For automated CI pipelines see the test-only `-c` preamble pattern in `tests/integration/test_phase12_cli_backfill_e2e.py`; do NOT modify production source.

Failure mode: command exits 1 with `Passwords do not match.` or `Admin user already exists. No changes made.` Re-run with a fresh email if the latter; re-run and retype carefully if the former.

---

## 6. Backfill Tasks

Purpose: every `tasks` row created under v1.1 has `user_id IS NULL`. Section 7's migration refuses to run while orphans exist (its pre-flight raises `RuntimeError`). This step reassigns every orphan to the admin user from Section 5.

Pre-flight check (admin must exist; chain head must be `0002_auth_schema`):

```bash
uv run alembic current
```

Expected output: `0002_auth_schema (head)`.

Step 6a — dry-run to see the count:

```bash
uv run python -m app.cli backfill-tasks --admin-email admin@example.com --dry-run
```

Expected output: `Would reassign <N> orphan tasks to admin admin@example.com (id=<id>). [dry-run]`

Step 6b — commit. The `--yes` flag skips the y/N confirmation prompt for scripted runbooks:

```bash
uv run python -m app.cli backfill-tasks --admin-email admin@example.com --yes
```

Expected output: `Reassigned <N> orphan tasks to admin admin@example.com (id=<id>).`

Exit code: 0 on success. Exit 1 if the post-condition `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL` is non-zero (the transaction rolls back automatically — fail-loud).

Verify zero orphans remain:

```bash
sqlite3 records.db "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL;"
```

Expected output: `0`.

Idempotency: re-running with zero orphans exits 0 with the message `No orphan tasks to backfill.` Safe to retry.

Failure mode: `Admin user not found: admin@example.com` (re-run Section 5 with the matching email); or `verification failed: <N> orphan tasks still remain` (database is in an inconsistent state — restore from backup and investigate before retrying).

---

## 7. Upgrade Head (Apply NOT NULL)

Purpose: tighten `tasks.user_id` to `NOT NULL` and create the `idx_tasks_user_id` index. The migration pre-flight re-checks `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL` and refuses to alter the column if any orphans exist.

Pre-flight check (zero orphans must remain from Section 6):

```bash
sqlite3 records.db "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL;"
```

Expected output: `0`. If non-zero, return to Section 6.

Run the final upgrade:

```bash
uv run alembic upgrade head
```

Expected output:

```
INFO  [alembic.runtime.migration] Running upgrade 0002_auth_schema -> 0003_tasks_user_id_not_null, tasks_user_id_not_null
```

Verify the chain landed at head:

```bash
uv run alembic current
```

Expected output: `0003_tasks_user_id_not_null (head)`.

If the pre-flight guard fires (you skipped Section 6), Alembic surfaces:

```text
RuntimeError: Refusing to apply 0003_tasks_user_id_not_null:
<N> tasks have user_id IS NULL. Run
`python -m app.cli backfill-tasks --admin-email <e>` first.
```

Recovery: run Section 6, then re-run `uv run alembic upgrade head`. The migration is idempotent at this boundary — the failed pre-flight aborts BEFORE any schema change.

Failure mode: any other `IntegrityError` indicates schema drift. Restore from backup (Section 9, option B) and investigate.

---

## 8. Smoke Verify

Purpose: confirm the migration landed cleanly. Every check below should pass; any failure means the migration is incomplete.

Check 1 — chain at head:

```bash
uv run alembic current
```

Expected output: `0003_tasks_user_id_not_null (head)`.

Check 2 — every `tasks` row has a `user_id`:

```bash
sqlite3 records.db "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL;"
```

Expected output: `0`.

Check 3 — `idx_tasks_user_id` exists:

```bash
sqlite3 records.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks';"
```

Expected output (set; order may vary): a list including `idx_tasks_user_id` alongside any `sqlite_autoindex_*` entries.

Check 4 — admin user exists with `plan_tier='pro'`:

```bash
sqlite3 records.db "SELECT id, email, plan_tier FROM users WHERE email='admin@example.com';"
```

Expected output: `<id>|admin@example.com|pro`.

Check 5 — foreign-key enforcement is active (the production engine listener enables `PRAGMA foreign_keys=ON` at boot; manual confirmation):

```bash
sqlite3 records.db "PRAGMA foreign_keys;"
```

Expected output: `1` after the application boots; SQLite default is `0` for ad-hoc CLI sessions, so the value seen here may be `0`. The application's engine listener (`app/infrastructure/database/connection.py`) enforces it at runtime.

Check 6 — application boots cleanly (Alembic is the schema source of truth — `Base.metadata.create_all` was removed in Phase 10):

```bash
uv run uvicorn app.main:app --port 8000
```

Expected output: startup logs end with `Application startup complete.` with no schema errors. Stop with `Ctrl+C`. The v1.2 frontend at `/ui` will require login on the next request.

Check 7 — v1.2 auth surface is mounted (boundary assert: every preceding check passes regardless of `AUTH__V2_ENABLED`; this one fires only when the master gate is set):

```bash
curl -i -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"smoke-pw-1234"}'
```

Expected output: `HTTP/1.1 201 Created` (registration succeeded) OR `HTTP/1.1 400/422` (validation rejected the body) — anything except `HTTP/1.1 404 Not Found`. A 404 here means `AUTH__V2_ENABLED=false` (or unset) in the running env: the v1.2 routers in `app/main.py:247-252` never mounted. Fix `.env` per Section 1's pre-requisite checklist and restart.

Failure mode: any check above failing means the migration is incomplete. Roll back via Section 9 and investigate before retrying.

---

## 9. Rollback

Two rollback paths. Pick based on how far the migration progressed and whether downstream data was written.

**Option A — Reversible step-back via Alembic (preferred when no v1.2 user data has been created):**

Reverse the most recent migration:

```bash
uv run alembic downgrade -1
```

Expected output: `INFO [alembic.runtime.migration] Running downgrade <from> -> <to>, ...`

Step further back as needed:

```bash
uv run alembic downgrade 0002_auth_schema
```

Expected output: `Running downgrade 0003_tasks_user_id_not_null -> 0002_auth_schema, tasks_user_id_not_null` — drops `idx_tasks_user_id`, restores `tasks.user_id` to nullable.

```bash
uv run alembic downgrade 0001_baseline
```

Expected output: `Running downgrade 0002_auth_schema -> 0001_baseline, auth_schema` — drops the six auth tables AND drops the `tasks.user_id` column. Backfilled `tasks.user_id` values are LOST on this step.

```bash
uv run alembic downgrade base
```

Expected output: `Running downgrade 0001_baseline -> , baseline` — drops the `tasks` table itself. Only safe on a freshly-created (greenfield) DB; on a v1.1 brownfield DB this loses every task row. Do NOT run on production data — use option B instead.

**Option B — Full restore from backup (use when the migration is unrecoverable mid-procedure or v1.2 writes already happened):**

Stop the application, then restore the pre-v1.2 backup over the current DB:

```bash
cp records.db.pre-v1.2.bak records.db
```

Expected output: silent success.

Verify the restore:

```bash
sqlite3 records.db "SELECT COUNT(*) FROM tasks;"
```

Expected output: the same row count seen in Section 2's verify step.

```bash
sqlite3 records.db ".tables"
```

Expected output: only the v1.1 tables (no `users`, `api_keys`, etc.) — the backup pre-dates Section 4.

After option B the chain is back to its pre-stamp state. Re-stamping is NOT required if you are reverting to a v1.1 deploy. Re-stamp (Section 3) only if you intend to retry the v1.2 migration immediately.

Failure mode: if `cp` fails on restore, the live DB may be partially upgraded with no backup safety net. Stop all writers and inspect file locks, disk space, and permissions before any further action.

---

*Phase 17 OPS-03 — generated 2026-05-01.*
*Step ordering mirrors `tests/integration/test_migration_smoke.py` (VERIFY-08, executable proof-of-runbook).*
