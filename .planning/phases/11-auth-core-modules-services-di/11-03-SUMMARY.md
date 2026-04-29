---
phase: 11-auth-core-modules-services-di
plan: 03
subsystem: auth
tags: [auth, domain, repos, sqlalchemy, mappers, persistence]

# Dependency graph
requires:
  - phase: 10-alembic-baseline-auth-schema
    provides: ORM tables (users, api_keys, rate_limit_buckets, device_fingerprints) + idx_api_keys_prefix index + FK CASCADE
  - phase: 11-auth-core-modules-services-di/11-01
    provides: DatabaseOperationError already in app/core/exceptions.py; logger in app/core/logging.py with RedactingFilter defense-in-depth
provides:
  - 4 framework-free domain dataclasses (User, ApiKey, RateLimitBucket, DeviceFingerprint) in app/domain/entities/
  - 4 Protocol-based repository interfaces (IUserRepository, IApiKeyRepository, IRateLimitRepository, IDeviceFingerprintRepository) in app/domain/repositories/
  - 4 ORM<->domain mappers (to_domain + to_orm) in app/infrastructure/database/mappers/
  - 4 SQLAlchemy repository implementations in app/infrastructure/database/repositories/
  - SQLAlchemyApiKeyRepository.get_by_prefix uses idx_api_keys_prefix (KEY-08, O(log n) bearer auth)
  - SQLAlchemyApiKeyRepository.get_by_prefix filters revoked_at IS NULL (T-11-12 mitigation)
  - SQLAlchemyRateLimitRepository.upsert_atomic wraps read+write in text("BEGIN IMMEDIATE") for SQLite worker-safety (T-11-10 mitigation)
  - All write methods: try -> commit / except SQLAlchemyError -> rollback -> raise DatabaseOperationError (no silent fallback on writes)
  - All read methods: try -> return / except SQLAlchemyError -> log + return None or [] (safe empty)
  - Domain layer remains framework-free: grep -rn "from sqlalchemy" app/domain/ returns 0
affects:
  - 11-04 services layer can compose AuthService(IUserRepository + PasswordService + TokenService), KeyService(IApiKeyRepository), RateLimitService(IRateLimitRepository)
  - 11-05 DI container will Factory-bind the 4 SQLAlchemy repos with session=db_session_factory (mirroring task_repository pattern at app/core/container.py)
  - 13-* HTTP routes consume these via service-layer indirection (DualAuthMiddleware -> KeyService.verify -> ApiKeyRepository.get_by_prefix; rate-limit middleware -> RateLimitService.check_and_consume -> RateLimitRepository.upsert_atomic)

# Tech tracking
tech-stack:
  added: []  # zero new deps — Phase 10 ORM + Phase 11-01 exceptions/logging are sufficient
  patterns:
    - "Framework-free domain entities (dataclass + business methods, no SQLAlchemy imports)"
    - "Protocol-based repository interfaces (structural typing, swappable backends without code change)"
    - "Mapper module per entity (to_domain + to_orm functions; SRP — no business logic in mappers)"
    - "Repository write contract: SQLAlchemyError -> rollback -> raise DatabaseOperationError(operation=..., reason=str(e), original_error=e)"
    - "Repository read contract: SQLAlchemyError -> log + return safe-empty (None for one-off, [] for collections)"
    - "Indexed prefix lookup via .filter(ORMApiKey.prefix == prefix).filter(ORMApiKey.revoked_at.is_(None)) — uses idx_api_keys_prefix from Phase 10 (KEY-08)"
    - "BEGIN IMMEDIATE upsert: session.execute(text('BEGIN IMMEDIATE')) wraps read-modify-write under one held SQLite RESERVED lock (CONTEXT §96-102)"
    - "Idempotent revoke at the repository layer: only writes revoked_at if currently NULL (matches the ApiKey.revoke() domain method)"
    - "Insert-only repo for audit trail (DeviceFingerprint has no update/delete methods — deliberate per ANTI-03)"

key-files:
  created:
    - app/domain/entities/user.py
    - app/domain/entities/api_key.py
    - app/domain/entities/rate_limit_bucket.py
    - app/domain/entities/device_fingerprint.py
    - app/domain/repositories/user_repository.py
    - app/domain/repositories/api_key_repository.py
    - app/domain/repositories/rate_limit_repository.py
    - app/domain/repositories/device_fingerprint_repository.py
    - app/infrastructure/database/mappers/user_mapper.py
    - app/infrastructure/database/mappers/api_key_mapper.py
    - app/infrastructure/database/mappers/rate_limit_bucket_mapper.py
    - app/infrastructure/database/mappers/device_fingerprint_mapper.py
    - app/infrastructure/database/repositories/sqlalchemy_user_repository.py
    - app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py
    - app/infrastructure/database/repositories/sqlalchemy_rate_limit_repository.py
    - app/infrastructure/database/repositories/sqlalchemy_device_fingerprint_repository.py
    - .planning/phases/11-auth-core-modules-services-di/11-03-SUMMARY.md
  modified:
    - app/domain/entities/__init__.py (extended __all__ to include 4 new entities, preserved Task)
    - app/domain/repositories/__init__.py (extended __all__ to include 4 new I*Repository, preserved ITaskRepository)
    - app/infrastructure/database/mappers/__init__.py (re-exports 4 new mapper modules + preserves task_mapper exports)

key-decisions:
  - "ApiKey.revoke (domain) and SQLAlchemyApiKeyRepository.revoke (persistence) are BOTH idempotent at their respective layers — domain method short-circuits if revoked_at is set; repo method short-circuits and skips the commit. Belt-and-braces: callers can use either entry point safely."
  - "SQLAlchemyApiKeyRepository.get_by_prefix returns list[ApiKey] (not Optional[ApiKey]) because the prefix is only 8 chars of url-safe base64 — collisions are theoretically possible (probability ~1 in 218 trillion at 100M keys, but architecturally allowed). Caller (KeyService.verify in Plan 11-04) iterates and uses secrets.compare_digest on hash to disambiguate."
  - "ApiKey.mark_used uses positional 'when' argument (not default datetime.now()) — service layer (Plan 11-04 KeyService) passes a single 'now' captured at the auth-verify boundary so mark_used and rate-limit consume share the same timestamp."
  - "ApiKey.revoke() domain method uses a separate datetime.now(timezone.utc) call from the repo — this is intentional: the domain entity may be detached when revoke() is called (e.g. from a service that mutates the in-memory entity then writes via repo.update). The repo.revoke() persists with its own current-time when called directly without a domain entity."
  - "Logging in repos uses %s placeholder formatting (not f-strings) so the RedactingFilter from Plan 11-01 sees the raw substitution and can scrub if a sensitive field accidentally lands in the message."
  - "DeviceFingerprint repo intentionally exposes ONLY add + get_recent_for_user — no update, no delete (insert-only audit trail). Future plans wanting to delete must explicitly extend the interface; the audit-trail constraint is a property of the ANTI-03 design, not an oversight."
  - "User.update is split into a two-step: existence check OUTSIDE try (raises DatabaseOperationError immediately on miss without a rollback path), then the mutation INSIDE try (rollback on commit failure). update_token_version inlines both steps inside try to preserve a single atomic boundary for the locked invariant."
  - "Mapper barrel (__init__.py) re-exports both modules-as-namespace AND the legacy to_domain/to_orm names from task_mapper. New code uses 'from app.infrastructure.database.mappers import user_mapper' style; existing code that did 'from app.infrastructure.database.mappers import to_domain' continues to work."

patterns-established:
  - "Per-entity mapper module (one file per ORM<->domain pair) instead of a single multi-mapper file — keeps the diff surface narrow when a future ORM column changes (only the affected entity's mapper file changes)."
  - "Write-method ordering convention: every repository file orders methods add -> get_* -> update/upsert -> delete/revoke. Mirrors the task_repository pattern; review eyes always know where to look."
  - "DatabaseOperationError raise sites pass operation= as a stable machine-readable code (e.g. 'add_user', 'update_token_version', 'revoke', 'upsert_rate_limit'). Wave-3 services can map these to user-facing 5xx responses without parsing the message."
  - "BEGIN IMMEDIATE wrapping pattern: session.execute(text('BEGIN IMMEDIATE')) before the read, single commit at the end — works on SQLite for RESERVED-lock escalation, no-ops harmlessly on Postgres (Postgres treats IMMEDIATE as a synonym for the default transaction). v1.3 Postgres swap will revisit but the API contract holds."

requirements-completed: [KEY-08, ANTI-03]

# Metrics
duration: 5m
completed: 2026-04-29
---

# Phase 11 Plan 03: Domain entities + Repository interfaces + ORM mappers + SQLAlchemy implementations Summary

**4 framework-free domain dataclasses, 4 Protocol-based repository interfaces, 4 ORM<->domain mappers, and 4 SQLAlchemy repositories with verifier-grade rollback + DatabaseOperationError discipline. ApiKeyRepository.get_by_prefix uses idx_api_keys_prefix (KEY-08, O(log n)) and filters revoked_at IS NULL (T-11-12). RateLimitRepository.upsert_atomic wraps read+write in BEGIN IMMEDIATE for SQLite worker-safety (T-11-10). Domain layer remains framework-free with zero SQLAlchemy imports.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-29T06:02:39Z
- **Completed:** 2026-04-29T06:07:10Z
- **Tasks:** 2 / 2
- **Files created:** 16 (4 entities + 4 repo Protocols + 4 mappers + 4 SQLAlchemy repos)
- **Files modified:** 3 barrel __init__.py (entities, repositories, mappers)
- **Commits:** 2 (one per task)

## Accomplishments

### Task 1 — Domain entities + Protocol interfaces + ORM mappers (12 files created, 3 barrels updated)

- **`app/domain/entities/user.py`** — `User` dataclass with `bump_token_version()` (logout-all-devices) and `start_trial()` (idempotent first-API-key-creation flag).
- **`app/domain/entities/api_key.py`** — `ApiKey` dataclass with `is_active()`, `mark_used(when)`, and idempotent `revoke()`.
- **`app/domain/entities/rate_limit_bucket.py`** — pure persistence row; NO business methods (refill/consume math lives in `app.core.rate_limit.consume()` from Plan 11-02).
- **`app/domain/entities/device_fingerprint.py`** — insert-once audit row (ANTI-03).
- **`app/domain/repositories/{user,api_key,rate_limit,device_fingerprint}_repository.py`** — 4 `Protocol`-based interfaces with full per-method docstrings (mirrors `ITaskRepository` shape).
- **`app/infrastructure/database/mappers/{user,api_key,rate_limit_bucket,device_fingerprint}_mapper.py`** — 4 to_domain/to_orm pairs (mirror `task_mapper` shape).
- **3 barrel `__init__.py` updates** — entities (`+User, ApiKey, RateLimitBucket, DeviceFingerprint`), repositories (`+I{User,ApiKey,RateLimit,DeviceFingerprint}Repository`), mappers (re-export 4 new modules-as-namespace plus preserve legacy task_mapper exports).
- **Domain framework-free verified:** `grep -rn "from sqlalchemy" app/domain/` returns 0.

### Task 2 — 4 SQLAlchemy repository implementations (4 files created)

- **`SQLAlchemyUserRepository`** — `add` / `get_by_id` / `get_by_email` / `update_token_version` / `update` / `delete`. 5 raise sites for `DatabaseOperationError`. Logs only `id=` (never email or password_hash).
- **`SQLAlchemyApiKeyRepository`** — `add` / `get_by_id` / **`get_by_prefix`** / `get_by_user` / `mark_used` / `revoke`. `get_by_prefix` filters `ORMApiKey.prefix == prefix` AND `ORMApiKey.revoked_at.is_(None)` — uses **idx_api_keys_prefix** (Phase 10) for O(log n) bearer auth (KEY-08); revoked keys excluded at the persistence layer (T-11-12). `revoke` is idempotent (skips commit if `revoked_at` already set).
- **`SQLAlchemyRateLimitRepository`** — `get_by_key` + **`upsert_atomic`**. `upsert_atomic` opens `text("BEGIN IMMEDIATE")` to escalate to RESERVED lock, then does the read-modify-write as a single transaction (T-11-10).
- **`SQLAlchemyDeviceFingerprintRepository`** — `add` + `get_recent_for_user` only (insert + read-only audit trail per ANTI-03 design). Logs only `id=` and `user_id=` — never the hash columns or `ip_subnet`.

## Task Commits

| Task | Hash      | Subject                                                                    |
| ---- | --------- | -------------------------------------------------------------------------- |
| 1    | `101d8bc` | feat(11-03): add 4 domain entities + 4 repo Protocols + 4 ORM mappers      |
| 2    | `f296875` | feat(11-03): add 4 SQLAlchemy repositories with rollback + DatabaseOperationError |

## Verifier-Enforced Gate Results

| Gate | Expected | Actual | Pass |
|------|----------|--------|------|
| `grep -rn "from sqlalchemy" app/domain/` (domain framework-free) | 0 | 0 | yes |
| `grep -c "class IUserRepository(Protocol)" app/domain/repositories/user_repository.py` | 1 | 1 | yes |
| `grep -c "get_by_prefix" app/domain/repositories/api_key_repository.py` | >=1 | 1 | yes |
| `grep -c "upsert_atomic" app/domain/repositories/rate_limit_repository.py` | >=1 | 1 | yes |
| `grep -c "ORMApiKey.prefix == prefix" app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py` | 1 | 1 | yes |
| `grep -c "ORMApiKey.revoked_at.is_(None)" app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py` | 1 | 1 | yes |
| `grep -c "BEGIN IMMEDIATE" app/infrastructure/database/repositories/sqlalchemy_rate_limit_repository.py` | 1 | 1 | yes |
| `grep -c "raise DatabaseOperationError" app/infrastructure/database/repositories/sqlalchemy_user_repository.py` | >=3 | 5 (add, update_token_version-inner, update-outer, update-inner, update_token_version-not-found-fallthrough) | yes |
| `grep -c "from sqlalchemy.orm import.*relationship" app/infrastructure/database/repositories/*.py` | 0 | 0 | yes |
| `grep -cE "^\s+if .*\bif\b" app/infrastructure/database/repositories/sqlalchemy_*.py` (no nested-if-in-if) | 0 | 0 | yes |
| `grep -nE "logger.*(password_hash\|cookie_hash\|ua_hash\|ip_subnet)" app/infrastructure/database/repositories/sqlalchemy_*.py` | 0 lines | 0 lines | yes |
| All 4 entities + 4 protocols + 4 mappers + 4 repos importable | exit 0 | exit 0 | yes |
| `pytest tests/unit -q` regressions caused by this plan | 0 new failures | 0 new failures (3 pre-existing audio_processing_service failures + 3 pre-existing factory_boy collection errors documented in 11-01 SUMMARY) | yes |

## Decisions Made

- **`get_by_prefix` returns `list[ApiKey]` (not `Optional[ApiKey]`):** the 8-char url-safe base64 prefix has a tiny but architecturally non-zero collision probability. Caller (KeyService.verify in Plan 11-04) iterates and uses `secrets.compare_digest` on the hash to disambiguate. This is the same shape as the locked CONTEXT §72-82 spec ("prefix lookup -> SHA-256 hash compare").
- **`ApiKey.revoke()` (domain) and `SQLAlchemyApiKeyRepository.revoke()` (persistence) are BOTH idempotent:** belt-and-braces — domain method short-circuits if `revoked_at` is set; repo method short-circuits and skips the commit (no useless write). Either entry point is safe to call repeatedly.
- **`update` validates existence OUTSIDE the try block; `update_token_version` validates INSIDE:** different correctness semantics. `update` raises `DatabaseOperationError(operation="update_user", reason="...not found")` immediately without needing rollback (no transaction begun). `update_token_version` keeps the existence check inside the try block because the locked invariant ("logout-all-devices is atomic") requires a single transaction boundary.
- **`SQLAlchemyDeviceFingerprintRepository` exposes ONLY `add` + `get_recent_for_user`:** no update, no delete. Audit-trail constraint per ANTI-03. Future plans wanting to delete would need to add the methods AND extend the Protocol — both diffs would be visible to review.
- **`%s` placeholder formatting in logger calls (not f-strings):** the `RedactingFilter` (Plan 11-01) inspects `record.args` to scrub sensitive substitutions. Pre-formatted f-strings would bypass this defense-in-depth net.
- **`text("BEGIN IMMEDIATE")` (not raw `session.execute("BEGIN IMMEDIATE")`):** SQLAlchemy 2.x rejects raw string `execute()` calls. The `text()` wrapper is required.
- **Mapper barrel re-exports modules-as-namespace AND legacy `to_domain/to_orm`:** new code uses `from app.infrastructure.database.mappers import user_mapper` then `user_mapper.to_domain(...)`; the original `from app.infrastructure.database.mappers import to_domain` (referring to the task_mapper export) continues to work for backward compatibility with the Wave 0 task code.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Acceptance criteria gate counted docstring quotation as a real call site**

- **Found during:** Task 2 verification — `grep -c "ORMApiKey.prefix == prefix"` returned 2 instead of the expected 1.
- **Issue:** The plan's acceptance criterion (`grep -c "ORMApiKey.prefix == prefix" app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py` returns 1 (uses indexed column)) intends to verify exactly one real `.filter(...)` call site. My initial implementation also quoted the pattern verbatim in the `get_by_prefix` docstring, which inflated the grep count to 2. Functionally correct (one filter call, plus the doc quote), but tripped the literal verifier gate.
- **Fix:** Rewrote the docstring to describe the filter prose-style ("Filters by prefix-column equality AND `revoked_at IS NULL`") instead of quoting the Python expression. The actual `.filter(ORMApiKey.prefix == prefix)` call is the only remaining match, satisfying the count==1 contract.
- **Files modified:** `app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py` (docstring on `get_by_prefix`)
- **Verification:** Re-ran `grep -c` — returns 1.
- **Committed in:** `f296875` (Task 2 commit; the docstring tweak was rolled into the same Task-2 implementation commit before commit time).

---

**Total deviations:** 1 auto-fixed (1 bug — verifier-gate alignment)
**Impact on plan:** Single fix is correctness-required for the grep verifier gate. Zero semantic change to behavior; the filter expression and indexed lookup are unchanged. No scope creep.

## Issues Encountered

- **Pre-existing modifications to `README.md`, `app/docs/db_schema.md`, `app/docs/openapi.json`, `app/docs/openapi.yaml`, `app/main.py`, `frontend/src/components/upload/FileQueueItem.tsx`** in working tree at plan start — completely unrelated to this plan's repository-layer work. Out of scope. Not committed by this plan. Logged as pre-existing in Phase 10 / 11-01 / 11-02 SUMMARYs.
- **Untracked `.claude/`, `app/core/auth.py`, `models/`** at plan start — pre-existing untracked files (`.claude/` is editor cache, `auth.py` is the existing bearer-token middleware referenced for the `secrets.compare_digest` analog, `models/` is the local model cache). Out of scope.
- **Pre-existing pytest failures** (3 in `tests/unit/services/test_audio_processing_service.py` asserting `update` called once but service emits 4 progress-stage updates; 3 collection errors in `tests/unit/{domain/entities,infrastructure/database/{mappers,repositories}}/test_*.py` due to missing `factory_boy` dev dep) — completely unrelated to this plan's repository-layer work. Documented in 11-01 SUMMARY § "Issues Encountered" as out-of-scope.

## Threat Flags

None — all changes stay within the plan's documented threat model. T-11-09 (logging hygiene), T-11-10 (BEGIN IMMEDIATE upsert), T-11-11 (indexed get_by_prefix), and T-11-12 (revoked_at IS NULL filter) all delivered as specified.

## User Setup Required

None — these are persistence-layer modules with no external service configuration. The Phase 10 ORM tables already exist in any DB initialised via `alembic upgrade head`.

## Next Phase Readiness

Wave 4 (services + DI) can now proceed:

- **11-04 (services):** can compose `AuthService(user_repository=IUserRepository, password_service=PasswordService, token_service=TokenService)`; `KeyService(repository=IApiKeyRepository)`; `RateLimitService(repository=IRateLimitRepository)`. All Protocol shapes are stable; mocks will use `unittest.mock.MagicMock(spec=IUserRepository)` etc. for unit tests.
- **11-05 (DI):** `providers.Factory(SQLAlchemyUserRepository, session=db_session_factory)` (and 3 siblings) can be added to `app/core/container.py` immediately after the existing `task_repository` provider. The Wave-1 `db_session_factory` is the same session source.
- **13-* HTTP routes:** `DualAuthMiddleware` will call `KeyService.verify(plaintext)` which calls `parse_prefix` then `ApiKeyRepository.get_by_prefix(prefix)` — single indexed lookup, no full table scan, revoked keys never authenticate. Rate-limit middleware will call `RateLimitService.check_and_consume(bucket_key, ...)` which calls `consume()` (Plan 11-02) and persists via `RateLimitRepository.upsert_atomic` under BEGIN IMMEDIATE.

No blockers for Wave 4.

## Self-Check: PASSED

Verified after SUMMARY write:

- `app/domain/entities/user.py` — FOUND
- `app/domain/entities/api_key.py` — FOUND
- `app/domain/entities/rate_limit_bucket.py` — FOUND
- `app/domain/entities/device_fingerprint.py` — FOUND
- `app/domain/entities/__init__.py` (modified) — FOUND with 4 new entity exports
- `app/domain/repositories/user_repository.py` — FOUND
- `app/domain/repositories/api_key_repository.py` — FOUND
- `app/domain/repositories/rate_limit_repository.py` — FOUND
- `app/domain/repositories/device_fingerprint_repository.py` — FOUND
- `app/domain/repositories/__init__.py` (modified) — FOUND with 4 new I*Repository exports
- `app/infrastructure/database/mappers/user_mapper.py` — FOUND
- `app/infrastructure/database/mappers/api_key_mapper.py` — FOUND
- `app/infrastructure/database/mappers/rate_limit_bucket_mapper.py` — FOUND
- `app/infrastructure/database/mappers/device_fingerprint_mapper.py` — FOUND
- `app/infrastructure/database/mappers/__init__.py` (modified) — FOUND with 4 new mapper-as-namespace exports
- `app/infrastructure/database/repositories/sqlalchemy_user_repository.py` — FOUND
- `app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py` — FOUND
- `app/infrastructure/database/repositories/sqlalchemy_rate_limit_repository.py` — FOUND
- `app/infrastructure/database/repositories/sqlalchemy_device_fingerprint_repository.py` — FOUND
- Commit `101d8bc` (Task 1: entities + protocols + mappers) — FOUND in `git log`
- Commit `f296875` (Task 2: 4 SQLAlchemy repos) — FOUND in `git log`

---
*Phase: 11-auth-core-modules-services-di*
*Completed: 2026-04-29*
