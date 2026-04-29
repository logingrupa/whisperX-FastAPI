---
phase: 11-auth-core-modules-services-di
plan: 04
subsystem: auth
tags: [auth, services, di, container, tdd]

# Dependency graph
requires:
  - phase: 11-auth-core-modules-services-di/11-01
    provides: AuthSettings (JWT_SECRET, JWT_TTL_DAYS), 9 typed auth exceptions, RedactingFilter on whisperX logger
  - phase: 11-auth-core-modules-services-di/11-02
    provides: 6 pure-logic core modules — password_hasher, jwt_codec, api_key, csrf, rate_limit, device_fingerprint
  - phase: 11-auth-core-modules-services-di/11-03
    provides: 4 domain entities, 4 IRepository Protocols, 4 SQLAlchemy repositories
provides:
  - app/services/auth/password_service.py — PasswordService (Singleton)
  - app/services/auth/token_service.py — TokenService(secret, ttl_days=7) (Singleton)
  - app/services/auth/auth_service.py — AuthService(IUserRepository + PasswordService + TokenService) (Factory)
  - app/services/auth/key_service.py — KeyService(IApiKeyRepository) (Factory)
  - app/services/auth/rate_limit_service.py — RateLimitService(IRateLimitRepository) (Factory)
  - app/services/auth/csrf_service.py — CsrfService (Singleton)
  - app/services/auth/__init__.py — barrel re-exporting all 6 service classes
  - DI Container providers — 4 repos (Factory) + 6 services (3 Singleton, 3 Factory)
  - 22 unit tests across 6 service-test files (3 + 4 + 5 + 4 + 3 + 3) all passing
  - Combined Phase 11 unit suite: 50 tests passing (28 core + 22 service)
affects:
  - 11-05 DI integration test will resolve all 6 services from Container() and assert types/identities
  - 13-* DualAuthMiddleware will resolve auth_service/key_service from Container — never instantiate directly
  - 13-* /auth/login + /auth/register routes call AuthService.{login,register}; map InvalidCredentialsError -> 401
  - 13-* /api/keys POST returns plaintext from KeyService.create_key (show-once UX)
  - 15-* AUTH-06 logout-all-devices wires AuthService.logout_all_devices

# Tech tracking
tech-stack:
  added: []  # zero new deps — all libraries already declared in 11-01
  patterns:
    - "Service layer = orchestration only; ZERO hash/jwt/argon2 logic in service files"
    - "Constructor injection — IUserRepository + PasswordService + TokenService passed in (no Settings() lookup)"
    - "Singleton vs Factory split — stateless services as Singleton (PasswordService, CsrfService, TokenService); stateful with repo deps as Factory (AuthService, KeyService, RateLimitService)"
    - "SecretStr unwrap at DI provide-time — config.provided.auth.JWT_SECRET.provided.get_secret_value.call() yields plain str so TokenService.__init__(secret: str) stays clean"
    - "Generic InvalidCredentialsError on both wrong-email and wrong-password paths (no enumeration via differential responses)"
    - "verify_password skipped on missing user — accepted timing trade-off (ANTI-02 throttles login)"
    - "create_key returns plaintext exactly once — caller responsible for show-once UX; service NEVER logs plaintext"
    - "Per-service RED→GREEN TDD pairs — 6 RED test commits + 6 GREEN feat commits + 1 container commit = 13 atomic commits"

key-files:
  created:
    - app/services/auth/__init__.py — barrel re-exporting 6 service classes
    - app/services/auth/password_service.py — Argon2id wrapper (PasswordService, Singleton)
    - app/services/auth/token_service.py — HS256 issue+verify_and_refresh (TokenService, Singleton)
    - app/services/auth/auth_service.py — register + login + logout_all_devices (AuthService, Factory)
    - app/services/auth/key_service.py — create_key (plaintext-once) + verify_plaintext + revoke_key + list_for_user (KeyService, Factory)
    - app/services/auth/rate_limit_service.py — check_and_consume (RateLimitService, Factory)
    - app/services/auth/csrf_service.py — issue + verify (CsrfService, Singleton)
    - tests/unit/services/auth/__init__.py — package marker
    - tests/unit/services/auth/test_password_service.py — 3 tests
    - tests/unit/services/auth/test_token_service.py — 4 tests
    - tests/unit/services/auth/test_auth_service.py — 5 tests
    - tests/unit/services/auth/test_key_service.py — 4 tests
    - tests/unit/services/auth/test_rate_limit_service.py — 3 tests
    - tests/unit/services/auth/test_csrf_service.py — 3 tests
    - .planning/phases/11-auth-core-modules-services-di/11-04-SUMMARY.md
  modified:
    - app/core/container.py — added 4 auth repo Factories + 6 auth service providers (3 Singleton + 3 Factory) + new imports

key-decisions:
  - "Per-service RED→GREEN TDD: 6 RED commits land an importless test file (ModuleNotFoundError on collection — proves test exercises a not-yet-existing module); 6 GREEN commits add the service implementation. Bundles match the plan's 'atomic commits per RED/GREEN cycle (12+ commits)' criterion."
  - "Barrel deferred during incremental TDD: app/services/auth/__init__.py contained only a docstring while services were being added one-by-one. If the barrel had eagerly imported all 6 from the start, RED tests for early services (PasswordService) would have failed not on the under-test import but on the package __init__ trying to load a not-yet-existing csrf_service. Final commit (CsrfService GREEN) finalizes the barrel re-exports — verifier sees the full barrel at plan tail."
  - "SecretStr unwrap via .provided.get_secret_value.call(): chosen as the locked path per CONTEXT §211 + plan body. Smoke-tested: Container().token_service().secret resolves to a plain str (len=18 for the dev default 'change-me-dev-only'). The fallback adapter approach was unnecessary — dependency-injector 4.x supports the .provided chain directly."
  - "AuthService.login skips verify_password on missing user (timing-oracle accepted): registered-vs-unregistered email is ~Argon2-time slower. Trade-off accepted because (a) ANTI-02 throttles login at 10/hr/IP making bulk enumeration impractical, (b) calling verify against a dummy hash to equalize timing wastes Argon2 CPU on every miss. Documented in service docstring + AuthService test asserts mock_password_service.verify_password is NOT called on missing-user path."
  - "AuthService.logout_all_devices raises InvalidCredentialsError on missing user (not a separate UserNotFoundError): callers in Phase 13 will already be authenticated, so this code path is only reachable on a race where a user is deleted between authentication and logout. Treating it as 'invalid credentials' avoids leaking 'user existed momentarily' info."
  - "KeyService.verify_plaintext catches the iterate-and-verify path inside the for loop (no nested if): the loop body has at most a single if guard before return; verifier-grep `^\\s+if .*\\bif\\b` returns 0 across all 6 service files."
  - "test fixtures use bare MagicMock() (no spec=...): keeps the test surface minimal. unittest.mock.MagicMock(spec=Protocol) raises 'Protocol cannot be used with isinstance' on 3.13; using bare mocks is the simplest approach matching test_task_management_service.py's existing pattern."
  - "TokenService.verify_and_refresh test secret length: bumped to 32+ chars to silence PyJWT InsecureKeyLengthWarning under HMAC; uses 'test-secret-at-least-32-bytes-long!' (35 chars). 11-02 jwt_codec tests still trip the warning intentionally to keep coverage of pre-RFC-compliant tokens."

patterns-established:
  - "Per-service RED→GREEN commit pairs (test(11-04): RED ... → feat(11-04): GREEN ... ): each pair stands alone in git log; bisect on a regression cleanly isolates the offending service."
  - "DI Container provider grouping: repositories first (4), then stateless Singletons (3), then stateful Factories (3). Mirrors the existing task_repository → task_management_service ordering. New code added strictly between task_management_service and ML services — no existing providers touched."
  - "Service-layer log discipline verified by grep gate: services log only id=, prefix= (e.g. ApiKey id=99 prefix=abc12345). Defense-in-depth via Plan 11-01 RedactingFilter still attached, but services don't rely on it."

requirements-completed: [AUTH-02, AUTH-08, AUTH-09, KEY-02, KEY-03, ANTI-03]

# Metrics
duration: 11m
completed: 2026-04-29
---

# Phase 11 Plan 04: 6 auth services + DI Container wiring Summary

**6 thin orchestration services (PasswordService/TokenService/AuthService/KeyService/RateLimitService/CsrfService) on top of Wave-2 core modules and Wave-3 repositories, plus 4 repository providers and 6 service providers wired into the DI Container with locked Singleton-vs-Factory lifecycles. All 22 service unit tests pass via mocked repositories. Generic InvalidCredentialsError on both login-fail legs (no enumeration). create_key returns plaintext exactly once. JWT_SECRET unwrapped at DI provide-time via SecretStr.get_secret_value.call(). Combined Phase 11 unit count: 50 tests (28 core + 22 service).**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-04-29T06:12:03Z
- **Completed:** 2026-04-29T06:22:40Z
- **Tasks:** 2 / 2
- **Files created:** 14 (6 services + 1 service barrel + 6 service-test files + 1 test package marker)
- **Files modified:** 1 (app/core/container.py)
- **Commits:** 13 (6 RED `test(...)` + 6 GREEN `feat(...)` + 1 container `feat(...)`)

## Accomplishments

### Service 1 — `app/services/auth/password_service.py` (3 tests pass)

- `hash_password(plain) -> str`: delegates to `password_hasher.hash` (Argon2id PHC-string).
- `verify_password(plain, hashed) -> bool`: delegates to `password_hasher.verify` (constant-time, returns False on mismatch or malformed hash).
- Stateless — registered as `providers.Singleton(PasswordService)`.
- Logs only `"PasswordService.hash_password called"` at debug; never the plain password.

### Service 2 — `app/services/auth/token_service.py` (4 tests pass)

- `__init__(secret: str, ttl_days: int = 7)`: secret arrives via DI from `config.provided.auth.JWT_SECRET` unwrapped via SecretStr.get_secret_value.
- `issue(user_id, token_version) -> str`: wraps `jwt_codec.encode_session`.
- `verify_and_refresh(token, current_token_version) -> (payload, new_token)`: wraps `jwt_codec.decode_session`, raises `JwtTamperedError` on token-version mismatch, re-issues via `self.issue(int(payload["sub"]), current_token_version)`.
- Singleton (the secret-bound instance is reused across requests).

### Service 3 — `app/services/auth/auth_service.py` (5 tests pass)

- `__init__(user_repository, password_service, token_service)`: 3-dep constructor injection.
- `register(email, plain_password) -> User`: get_by_email → raise UserAlreadyExistsError if found, else hash + add + return.
- `login(email, plain_password) -> (user, token)`: get_by_email → InvalidCredentialsError if missing → InvalidCredentialsError if verify_password False → token_service.issue(user.id, user.token_version).
- `logout_all_devices(user_id) -> None`: bumps token_version (AUTH-06).
- Logs only `id=N` — never email/password/token.
- Factory (one per request — bound to per-request session via repo).

### Service 4 — `app/services/auth/key_service.py` (4 tests pass)

- `__init__(repository)`: takes an IApiKeyRepository.
- `create_key(user_id, name) -> (plaintext, ApiKey)`: api_key.generate → persist (prefix + hash, never plaintext) → return plaintext exactly once.
- `verify_plaintext(plaintext) -> ApiKey`: parse_prefix → repo.get_by_prefix (indexed) → constant-time hash compare via api_key.verify → mark_used → return; raises InvalidApiKeyHashError on no match.
- `revoke_key(key_id)` + `list_for_user(user_id)`: pass-through to repo.
- Logs `id=`, `prefix=`, `user_id=` only — never plaintext or hash.
- Factory.

### Service 5 — `app/services/auth/rate_limit_service.py` (3 tests pass)

- `check_and_consume(bucket_key, *, tokens_needed, rate, capacity) -> bool`: get_by_key → seed at capacity if missing → rate_limit.consume (pure) → upsert_atomic (BEGIN IMMEDIATE under SQLite worker-safety) → return allowed flag.
- Logs only `bucket_key=` on denial — no user data.
- Factory.

### Service 6 — `app/services/auth/csrf_service.py` (3 tests pass)

- `issue() -> str`: wraps csrf.generate (urlsafe-base64 of 32 bytes).
- `verify(cookie_token, header_token) -> bool`: wraps csrf.verify (constant-time + empty-string short-circuit).
- Stateless — Singleton.

### DI Container — `app/core/container.py`

Imports added (4 repository classes + 6 service classes). Providers added in this exact order, between `task_management_service` and ML services:

| Order | Provider | Lifecycle | Class | Dependencies |
|---|---|---|---|---|
| 1 | `user_repository` | Factory | SQLAlchemyUserRepository | session=db_session_factory |
| 2 | `api_key_repository` | Factory | SQLAlchemyApiKeyRepository | session=db_session_factory |
| 3 | `rate_limit_repository` | Factory | SQLAlchemyRateLimitRepository | session=db_session_factory |
| 4 | `device_fingerprint_repository` | Factory | SQLAlchemyDeviceFingerprintRepository | session=db_session_factory |
| 5 | `password_service` | Singleton | PasswordService | (none) |
| 6 | `csrf_service` | Singleton | CsrfService | (none) |
| 7 | `token_service` | Singleton | TokenService | secret=config.provided.auth.JWT_SECRET.provided.get_secret_value.call() |
| 8 | `auth_service` | Factory | AuthService | user_repository, password_service, token_service |
| 9 | `key_service` | Factory | KeyService | api_key_repository |
| 10 | `rate_limit_service` | Factory | RateLimitService | rate_limit_repository |

Smoke-verified post-wire:

```text
Container().password_service() -> PasswordService instance ✓
Singletons: c.password_service() is c.password_service() -> True ✓
Singletons: c.token_service() is c.token_service() -> True ✓
TokenService.secret type: str, len=18 (the dev default 'change-me-dev-only')
```

## Task Commits

| Service / Step | RED hash | GREEN hash |
|---|---|---|
| PasswordService | `8900a25` (3 tests) | `95d4f67` |
| TokenService | `05b52f9` (4 tests) | `03bd60f` |
| AuthService | `00bc882` (5 tests) | `bb774f4` |
| KeyService | `8dd9644` (4 tests) | `373659c` |
| RateLimitService | `c1969f4` (3 tests) | `0b0d46f` |
| CsrfService | `9291bbe` (3 tests) | `d3582cc` (also finalizes barrel) |
| DI Container wire | — | `b6ab57d` |

13 commits total.

## Verifier-Enforced Gate Results

| Gate | Expected | Actual | Pass |
|------|----------|--------|------|
| `pytest tests/unit/services/auth/ -q` | 22 passed | 22 passed | yes |
| `pytest <Phase-11 core+service>` (28 core + 22 service) | 50 passed | 50 passed | yes |
| `python -c "from app.services.auth import AuthService, CsrfService, KeyService, PasswordService, RateLimitService, TokenService"` | exit 0 | exit 0 | yes |
| `python -c "from app.core.container import Container; c = Container(); s = c.password_service(); assert type(s).__name__ == 'PasswordService'"` | exit 0 | exit 0 | yes |
| `grep -rn "^import jwt$" app/services/` | 0 | 0 | yes |
| `grep -rn "import hashlib" app/services/auth/` | 0 | 0 | yes |
| `grep -rn "from app.core.config" app/services/auth/` | 0 | 0 | yes |
| `grep -nE "logger\.(info\|debug\|warning\|error).*(\bsecret\b\|JWT_SECRET\|whsk_\|password_hash\|\bhash\b\|cookie_hash\|ua_hash\|raw_token\|\bemail\b\|\bpassword\b)" app/services/auth/*.py` | 0 lines | 0 lines | yes |
| `grep -cE "^\s+if .*\bif\b" app/services/auth/*.py` | 0 | 0 | yes |
| `grep -c "secrets.compare_digest" app/services/auth/*.py` | 0 | 0 | yes |
| `grep -c "InvalidCredentialsError" app/services/auth/auth_service.py` | ≥3 | 5 (1 import + 2 login raises + 1 logout-all raise + 1 docstring) | yes |
| `grep -c "auth_service = providers.Factory" app/core/container.py` | 1 | 1 | yes |
| `grep -c "key_service = providers.Factory" app/core/container.py` | 1 | 1 | yes |
| `grep -c "rate_limit_service = providers.Factory" app/core/container.py` | 1 | 1 | yes |
| `grep -c "password_service = providers.Singleton" app/core/container.py` | 1 | 1 | yes |
| `grep -c "csrf_service = providers.Singleton" app/core/container.py` | 1 | 1 | yes |
| `grep -c "token_service = providers.Singleton" app/core/container.py` | 1 | 1 | yes |
| `grep -c "user_repository = providers.Factory" app/core/container.py` | 1 | 1 | yes |
| `grep -c "api_key_repository = providers.Factory" app/core/container.py` | 1 | 1 | yes |
| `grep -c "rate_limit_repository = providers.Factory" app/core/container.py` | 1 | 1 | yes |
| `grep -c "device_fingerprint_repository = providers.Factory" app/core/container.py` | 1 | 1 | yes |
| `pytest tests/unit -q` regressions caused by this plan | 0 new failures | 0 new failures | yes |

## Decisions Made

- **Per-service TDD bundling:** plan instructed `tdd="true"` on Task 1 + Task 2; success criteria locked at "12+ commits (6 services × 2 + container)". Implemented as 6 RED→GREEN pairs across the two tasks plus a 13th container-wiring commit. Each RED commit fails on `ModuleNotFoundError` for the under-test service module — proves test predates implementation.
- **Barrel finalization deferred to last GREEN commit:** `app/services/auth/__init__.py` was a docstring-only stub during incremental construction, so RED tests for PasswordService didn't fail on a not-yet-existing csrf_service import. Final CsrfService GREEN commit (`d3582cc`) replaces the stub with the full re-export barrel — verifier sees the locked CONTEXT §160 layout at plan tail.
- **SecretStr unwrap pattern via `.provided.get_secret_value.call()`:** plan's primary path. Smoke-test confirms `dependency-injector` 4.x resolves the chain correctly — no fallback adapter needed. Inline `# type: ignore` not required (the call() returns the string at runtime; type checkers may complain but the project is runtime-validated).
- **Bare MagicMock fixtures:** test files use `MagicMock()` instead of `MagicMock(spec=Protocol)` because Python 3.13 + `typing.Protocol` rejects `isinstance` against runtime-non-protocols. Matches the existing `tests/unit/services/test_task_management_service.py` style — minimal, no overconfiguration.
- **TokenService test secret bumped to 35 chars:** silences PyJWT InsecureKeyLengthWarning under HMAC. Doesn't materially change test semantics. The 11-02 jwt_codec tests intentionally use short secrets to exercise the warning path — keeping that coverage there.
- **AuthService.logout_all_devices raises InvalidCredentialsError on missing user:** treats race-deleted-mid-request as "invalid credentials" to avoid leaking "user existed once" info. Phase 13 should never reach this path under normal flow (caller is already authenticated).
- **Generic InvalidCredentialsError on both login fail-paths:** test_auth_service.py asserts `mock_password_service.verify_password.assert_not_called()` on missing-user path AND `pytest.raises(InvalidCredentialsError)` on wrong-password path. Both paths emit the same exception type with identical user_message.

## Deviations from Plan

None — plan executed exactly as written. All 13 commits land cleanly; all 22 service tests pass on first GREEN run; all gates green.

A note on **fixture spec=**: plan body line 793-808 wrote `mock_user_repo: MagicMock` without `spec=`. I followed the plan literally — using bare MagicMock — which matches the existing project test conventions and avoids 3.13's Protocol/isinstance friction. Not a deviation; just a documented choice consistent with the plan as written.

A note on **TokenService test secret length:** plan body line 745 wrote `secret="test-secret"` (11 chars). I bumped to 35 chars to silence the PyJWT 32-byte minimum warning. Test semantics unchanged. Recording here for traceability; not flagged as a deviation because the plan didn't lock secret length.

## Issues Encountered

- **Pre-existing modifications to `README.md`, `app/docs/db_schema.md`, `app/docs/openapi.json`, `app/docs/openapi.yaml`, `app/main.py`, `frontend/src/components/upload/FileQueueItem.tsx`** in working tree at plan start — completely unrelated to this plan's services/DI work. Out of scope. Not committed by this plan. Logged as pre-existing across all earlier Phase-11 SUMMARYs.
- **Untracked `.claude/`, `app/core/auth.py`, `models/`** at plan start — pre-existing untracked files; auth.py is the existing bearer-token middleware referenced as a `secrets.compare_digest` analog. Out of scope.
- **Pre-existing pytest failures** (3 in `tests/unit/services/test_audio_processing_service.py`; 3 collection errors in `tests/unit/{domain/entities,infrastructure/database/{mappers,repositories}}/test_*.py` due to missing `factory_boy` dev dep) — completely unrelated to this plan's auth services work. Documented in 11-01 SUMMARY § "Issues Encountered" as out-of-scope.
- **PyJWT InsecureKeyLengthWarning** in 4 jwt_codec tests (carry-over from 11-02): test secrets <32 bytes. Expected — doesn't affect test pass/fail; production secrets are enforced separately by `AuthSettings._reject_dev_defaults_in_production` from 11-01.

## Threat Flags

None — all changes stay within the plan's documented threat model. T-11-13 (no email enumeration via differential errors), T-11-14 (logout-all replay invalidated via token_version check), T-11-15 (sensitive-field log suppression), T-11-16 (SecretStr unwrap at DI boundary, never persisted in container surface) all delivered as specified.

Verified by grep:
- T-11-13: `grep -c "InvalidCredentialsError" app/services/auth/auth_service.py` → 5 (covers both login-fail legs).
- T-11-14: `grep -nE "ver.*current_token_version|token version mismatch" app/services/auth/token_service.py` → 1 line ("token version mismatch").
- T-11-15: log-hygiene grep returns 0 lines.
- T-11-16: `grep -nE "JWT_SECRET|SecretStr" app/services/auth/*.py` → 0 lines (services never see SecretStr or `JWT_SECRET` literal).

## User Setup Required

None — DI Container resolves all services using the existing AuthSettings dev defaults. Phase 17 owns production env runbook (`AUTH__JWT_SECRET=...` and `AUTH__CSRF_SECRET=...`).

## Next Phase Readiness

Wave-5 (Plan 11-05) and Phase 13 can now proceed:

- **11-05 (DI integration test + phase wrap-up):** can resolve all 6 services from `Container()` and assert each is the correct type with the correct dependencies wired. Smoke-test in this plan already proved `password_service`, `csrf_service`, `token_service` (Singletons) and the SecretStr unwrap chain. 11-05 will exercise the Factory services (AuthService/KeyService/RateLimitService) under a real db session.
- **13-* HTTP routes:** `DualAuthMiddleware` will resolve `key_service` from Container.wire(...); call `key_service.verify_plaintext(plaintext)` for bearer auth; resolve `auth_service` for `/auth/login` + `/auth/register`; resolve `rate_limit_service` for ANTI-02 + free-tier gates; resolve `csrf_service` for cookie-session protected routes.
- **15-* AUTH-06:** `auth_service.logout_all_devices(user_id)` is wired and tested.

No blockers for Wave-5 or Phase 13.

## Self-Check: PASSED

Verified after SUMMARY write:

- `app/services/auth/__init__.py` (modified) — FOUND with full barrel
- `app/services/auth/password_service.py` — FOUND
- `app/services/auth/token_service.py` — FOUND
- `app/services/auth/auth_service.py` — FOUND
- `app/services/auth/key_service.py` — FOUND
- `app/services/auth/rate_limit_service.py` — FOUND
- `app/services/auth/csrf_service.py` — FOUND
- `app/core/container.py` (modified) — FOUND with 4 repo Factories + 6 service providers
- `tests/unit/services/auth/__init__.py` — FOUND
- `tests/unit/services/auth/test_password_service.py` — FOUND (3 tests)
- `tests/unit/services/auth/test_token_service.py` — FOUND (4 tests)
- `tests/unit/services/auth/test_auth_service.py` — FOUND (5 tests)
- `tests/unit/services/auth/test_key_service.py` — FOUND (4 tests)
- `tests/unit/services/auth/test_rate_limit_service.py` — FOUND (3 tests)
- `tests/unit/services/auth/test_csrf_service.py` — FOUND (3 tests)
- Commit `8900a25` (RED PasswordService) — FOUND in `git log`
- Commit `95d4f67` (GREEN PasswordService) — FOUND
- Commit `05b52f9` (RED TokenService) — FOUND
- Commit `03bd60f` (GREEN TokenService) — FOUND
- Commit `00bc882` (RED AuthService) — FOUND
- Commit `bb774f4` (GREEN AuthService) — FOUND
- Commit `8dd9644` (RED KeyService) — FOUND
- Commit `373659c` (GREEN KeyService) — FOUND
- Commit `c1969f4` (RED RateLimitService) — FOUND
- Commit `0b0d46f` (GREEN RateLimitService) — FOUND
- Commit `9291bbe` (RED CsrfService) — FOUND
- Commit `d3582cc` (GREEN CsrfService + barrel finalize) — FOUND
- Commit `b6ab57d` (DI Container wire) — FOUND

## TDD Gate Compliance

- Each of 6 services: a `test(11-04): RED ...` commit precedes its `feat(11-04): GREEN ...` commit — verified via `git log --oneline | grep "(11-04)"`.
- No RED tests passed unexpectedly — each RED commit's pytest run failed with `ModuleNotFoundError: No module named 'app.services.auth.<module>'` at collection time, proving the test exercises a not-yet-existing module.
- No REFACTOR commits made (none needed; barrel finalize was bundled into the final GREEN commit).
- Plan 11-04 has `type: execute` in frontmatter (not `type: tdd` at plan level), but both tasks set `tdd="true"`; the 6-RED-then-6-GREEN-then-1-container sequence satisfies the per-task TDD discipline.

---
*Phase: 11-auth-core-modules-services-di*
*Completed: 2026-04-29*
