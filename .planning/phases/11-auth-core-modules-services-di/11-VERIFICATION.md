---
phase: 11-auth-core-modules-services-di
verified: 2026-04-29T09:42:00Z
status: passed
score: 14/14 must-haves verified
overrides_applied: 0
---

# Phase 11: Auth Core Modules + Services + DI — Verification Report

**Phase Goal:** Pure-logic auth/key/rate-limit/CSRF modules and services exist with single-source-of-truth invariants and pass unit tests; not yet wired into any HTTP route.
**Verified:** 2026-04-29T09:42:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | 6 pure-logic core modules exist and importable | VERIFIED | `password_hasher.py`, `jwt_codec.py`, `api_key.py`, `csrf.py`, `device_fingerprint.py`, `rate_limit.py` all present in `app/core/`; combined `from app.core import ...` succeeds (`ALL IMPORTS OK`) |
| 2  | Single `jwt.decode(` site in `app/` | VERIFIED | `grep -rn "jwt.decode("` returns 1 actual call (line 54 `app/core/jwt_codec.py`); 2 doc comments at lines 6/51 |
| 3  | DRY `_sha256_hex` helper | VERIFIED | `def _sha256_hex` defined exactly once at `app/core/_hashing.py:17`; consumed via `from app.core._hashing import _sha256_hex` in `api_key.py:13` and `device_fingerprint.py:14` |
| 4  | Argon2 hash round-trips with locked params (m=19456, t=2, p=1) | VERIFIED | Live test produced PHC string starting `$argon2id$v=19$m=19456,t=2,p=1$...`; `verify()` returned True for correct, False for wrong; module-load asserts at lines 21-23 |
| 5  | JWT rejects alg=none, tampered, expired tokens | VERIFIED | Live test triggered `JwtAlgorithmError` (alg=none / fallback `JwtTamperedError`), `JwtTamperedError` (signature corrupt), `JwtExpiredError` (past `exp`); pytest `test_jwt_codec.py` 4 cases pass |
| 6  | `whsk_<8>_<22>` 36-char keys + `secrets.compare_digest` | VERIFIED | Live `generate()` returned 36-char string `whsk_nUl2qyzG_...`; `verify()` uses `secrets.compare_digest` (`api_key.py:44`); module-load asserts at lines 23-26 |
| 7  | 4 domain entities + 4 Protocols + 4 mappers + 4 SQLAlchemy repos | VERIFIED | All present: `app/domain/entities/{user,api_key,rate_limit_bucket,device_fingerprint}.py`, `app/domain/repositories/{user,api_key,rate_limit,device_fingerprint}_repository.py`, mappers + `sqlalchemy_*_repository.py` mirror set |
| 8  | Domain framework-free | VERIFIED | `grep -rn "from sqlalchemy" app/domain/` returns 0 hits |
| 9  | 6 services in `app/services/auth/` | VERIFIED | `password_service.py`, `token_service.py`, `auth_service.py`, `key_service.py`, `rate_limit_service.py`, `csrf_service.py` all present; barrel `__init__.py` re-exports all 6 |
| 10 | DI Container resolves all 6 auth services | VERIFIED | Live `Container()` resolved instances of correct types: `PasswordService TokenService CsrfService AuthService KeyService RateLimitService`; exit 0 |
| 11 | Log redaction works at runtime | VERIFIED | `app/core/logging.py:50` runs `logger.addFilter(RedactingFilter())`; `tests/integration/test_phase11_log_redaction.py` 7 tests pass — assert `***REDACTED***` substituted in captured records |
| 12 | Argon2 benchmark <300ms p99 (VERIFY-05) | VERIFIED | `pytest -m slow tests/integration/test_argon2_benchmark.py` PASSED in 2.87s; assertion gate live |
| 13 | No HTTP wiring yet | VERIFIED | `grep` for `DualAuthMiddleware`, `/auth/login`, `@router.post(.*"/auth` returns 0 hits in `app/`; only legacy `BearerAuthMiddleware` (predates Phase 11) present in `app/core/auth.py` |
| 14 | Quality gates pass (no nested if-if; no `import jwt` in services; framework-free domain) | VERIFIED | `grep -cE "^\s+if .*\bif\b" app/core/*.py app/services/auth/*.py app/infrastructure/database/repositories/sqlalchemy_*.py` returns 0; `grep -rn "import jwt" app/services/` returns 0; `grep -rn "from sqlalchemy" app/domain/` returns 0 |

**Score:** 14/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | argon2-cffi + pyjwt deps | VERIFIED | `argon2-cffi>=23.1.0`, `pyjwt>=2.8.0` declared with phase tags |
| `app/core/config.py` | AuthSettings class + Settings.auth | VERIFIED | Live load: `JWT_SECRET present=True`, TTL=7, M=19456, T=2, P=1, CSRF present=True |
| `app/core/_hashing.py` | shared `_sha256_hex` | VERIFIED | Sole definition; both API key + device-fp consumers import |
| `app/core/_log_redaction.py` | RedactingFilter class | VERIFIED | Wired into `app/core/logging.py:50` via `logger.addFilter(RedactingFilter())` |
| `app/core/exceptions.py` | typed auth exceptions | VERIFIED | `InvalidCredentialsError`, `JwtAlgorithmError`, `JwtExpiredError`, `JwtTamperedError`, `InvalidApiKeyFormatError` etc. importable and raised in tests |
| `app/core/password_hasher.py` | Argon2id hash() + verify() | VERIFIED | Module-load asserts; live round-trip succeeds |
| `app/core/jwt_codec.py` | encode_session + decode_session — single jwt.decode site | VERIFIED | Sole production-call line 54; typed exception mapping |
| `app/core/api_key.py` | generate / verify / parse_prefix | VERIFIED | 36-char output; `secrets.compare_digest` |
| `app/core/csrf.py` | generate + verify (double-submit) | VERIFIED | `secrets.compare_digest` per pattern |
| `app/core/device_fingerprint.py` | compute → dict | VERIFIED | imports `ipaddress`; SHA-256 hashes |
| `app/core/rate_limit.py` | pure consume() | VERIFIED | TypedDict + pure function |
| `app/domain/entities/*.py` | 4 framework-free dataclasses | VERIFIED | User, ApiKey, RateLimitBucket, DeviceFingerprint present |
| `app/domain/repositories/*.py` | 4 Protocol interfaces | VERIFIED | All 4 Protocol files present |
| `app/infrastructure/database/mappers/*.py` | 4 mappers | VERIFIED | All 4 present |
| `app/infrastructure/database/repositories/sqlalchemy_*.py` | 4 SQLAlchemy repos | VERIFIED | All 4 present |
| `app/services/auth/*.py` | 6 services + barrel | VERIFIED | All 6 + `__init__.py` re-export |
| `app/core/container.py` | DI Container with 6 auth services + 4 repos | VERIFIED | Lines 97-136 wire all 4 repos + 6 services; live resolution succeeds |
| `tests/unit/core/*.py` | 6+ test files | VERIFIED | 9 test files (`test_api_key.py`, `test_config.py`, `test_container.py`, `test_csrf.py`, `test_device_fingerprint.py`, `test_exceptions.py`, `test_jwt_codec.py`, `test_password_hasher.py`, `test_rate_limit.py`) |
| `tests/unit/services/auth/*.py` | 6 service-test files | VERIFIED | All 6 present |
| `tests/integration/test_argon2_benchmark.py` | VERIFY-05 slow gate | VERIFIED | `@pytest.mark.slow` present; passes |
| `tests/integration/test_phase11_di_smoke.py` | DI resolution proof | VERIFIED | 7 tests pass; uses `isinstance(instance, ServiceClass)` pattern |
| `tests/integration/test_phase11_log_redaction.py` | end-to-end redaction | VERIFIED | 7 tests pass; asserts `***REDACTED***` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `app/core/logging.py` | `RedactingFilter` | `logger.addFilter()` | WIRED | Line 50: `logger.addFilter(RedactingFilter())` |
| `app/core/api_key.py` | `_hashing._sha256_hex` | import | WIRED | Line 13 import + lines 39, 44 usage |
| `app/core/device_fingerprint.py` | `_hashing._sha256_hex` | import | WIRED | Line 14 import |
| `app/core/container.py` | 6 service classes | `providers.Singleton/Factory` | WIRED | Lines 117-136 declarative providers; live resolution exits 0 |
| `app/core/container.py` | `Settings().auth.JWT_SECRET` | `config.provided.auth.JWT_SECRET.provided.get_secret_value.call()` | WIRED | Lines 119-122; TokenService receives string secret at runtime |
| `SQLAlchemyApiKeyRepository.get_by_prefix` | `idx_api_keys_prefix` index | `.filter(prefix == p).filter(revoked_at.is_(None))` | WIRED | Lines 73-74 of `sqlalchemy_api_key_repository.py` |
| `SQLAlchemyRateLimitRepository.upsert_atomic` | SQLite RESERVED lock | `text("BEGIN IMMEDIATE")` | WIRED | Line 57 |
| `tests/integration/test_phase11_di_smoke.py` | `Container()` | fresh instance + provider call | WIRED | Per-test fixture instantiates fresh Container; calls each provider |
| `tests/integration/test_argon2_benchmark.py` | `password_hasher.hash` | 100 timed calls | WIRED | Marked `@pytest.mark.slow`; PASS |

### Data-Flow Trace (Level 4)

Phase 11 produces pure-logic modules and services — no rendered/dynamic UI artifacts.
DI Container live resolution is the data-flow proxy: `Container() → password_service() → PasswordService(_HASHER instance)` — verified above.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Argon2 round-trip with locked params | `python -c "from app.core import password_hasher; ..."` | PHC `$argon2id$v=19$m=19456,t=2,p=1$...`; verify True/False as expected | PASS |
| JWT rejects alg=none/tampered/expired | live exception trigger | All three rejected with typed exceptions | PASS |
| API key 36-char `whsk_<8>_<22>` | live `api_key.generate()` | `len=36 prefix=nUl2qyzG`; verify True | PASS |
| AuthSettings loadable | live `Settings().auth` | secrets present, params 19456/2/1 | PASS |
| DI Container resolves 6 services | live `Container().{6 providers}()` | All 6 instantiate correct types | PASS |
| pytest `tests/unit/core` | `pytest -q` | 76 passed (≥27 threshold) | PASS |
| pytest `tests/unit/services/auth` | `pytest -q` | 22 passed (≥22 threshold) | PASS |
| pytest integration phase11 | `pytest -q` | 14 passed (di_smoke 7 + log_redaction 7) | PASS |
| pytest Argon2 benchmark slow | `pytest -m slow -q` | 1 passed (p99<300ms gate satisfied) | PASS |
| Combined phase 11 collected | `pytest --co` | 112 tests collected | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| AUTH-02 | 11-02, 11-04 | Argon2id `m=19456 KiB, t=2, p=1` | SATISFIED | Module-load asserts in `password_hasher.py:21-23`; live PHC verified |
| AUTH-08 | 11-02, 11-04 | All JWT decodes use `algorithms=["HS256"]` (single decode site) | SATISFIED | Single `jwt.decode(...)` call at `jwt_codec.py:54` with `algorithms=[_ALGORITHM]` |
| AUTH-09 | 11-01, 11-04, 11-05 | No raw passwords/JWT secrets/full API keys logged at any level | SATISFIED | `RedactingFilter` wired; `test_phase11_log_redaction.py` 7 tests pass with `***REDACTED***` assertion |
| KEY-02 | 11-02, 11-04 | `whsk_<8charPrefix>_<22charBase64>` (~128-bit entropy) | SATISFIED | Module asserts; `secrets.token_urlsafe(16)[:22]` = 22 urlsafe chars; live test 36 chars |
| KEY-03 | 11-02, 11-04 | SHA-256 hash storage; `secrets.compare_digest` verify | SATISFIED | `api_key.py:44` `secrets.compare_digest(_sha256_hex(plaintext), stored_hash)` |
| KEY-08 | 11-03 | Indexed prefix lookup (no full scan on bearer) | SATISFIED | `sqlalchemy_api_key_repository.py:73-74` `.filter(prefix == p).filter(revoked_at.is_(None))` — uses `idx_api_keys_prefix` from Phase 10 |
| ANTI-03 | 11-02, 11-03, 11-04 | device_fingerprints row at every login (cookie hash, UA SHA-256, IP /24, device_id) | SATISFIED | `device_fingerprint.py` produces required dict; `DeviceFingerprint` entity + repo + mapper present (login persistence is Phase 13's job — pure-logic readiness verified) |
| VERIFY-05 | 11-05 | Argon2 hash p99 <300ms (CI gate) | SATISFIED | `tests/integration/test_argon2_benchmark.py` `@pytest.mark.slow` gate passes |

All 8 requirements declared in plan frontmatters match REQUIREMENTS.md Phase 11 column. No orphans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | — |

Scans run on `app/core/{password_hasher,jwt_codec,api_key,csrf,device_fingerprint,rate_limit,_hashing,_log_redaction,container,exceptions}.py`, `app/services/auth/*.py`, `app/domain/**`, and 4 SQLAlchemy auth repos. Zero TODO/FIXME/PLACEHOLDER markers, zero `NotImplementedError`, zero stub returns, zero nested-if patterns.

### Human Verification Required

None. Phase produces pure-logic modules + services with full programmatic test coverage. UI/UX surfaces are Phase 13 (backend cutover) and Phase 14 (frontend cutover) territory.

### Gaps Summary

No gaps. All 14 must-haves and all 8 requirement IDs satisfied. Phase 11 goal — "Pure-logic auth/key/rate-limit/CSRF modules and services exist with single-source-of-truth invariants and pass unit tests; not yet wired into any HTTP route" — fully achieved.

Notable strengths:
- **Single-source-of-truth invariants enforced at module load** — `assert _M_COST == 19456`, `assert _TOTAL_LENGTH == 36`, `assert _ALGORITHM == "HS256"` fail loudly on drift.
- **Quality gates clean** — 0 nested-if, 0 `import jwt` in services, 0 `from sqlalchemy` in domain.
- **112 tests collected, all pass** (76 core + 22 services + 14 integration), benchmark slow-gate green.
- **HTTP wiring deliberately absent** — no `DualAuthMiddleware`, no `/auth/login`, no auth routes; Phase 13's job, not Phase 11's.

---

_Verified: 2026-04-29T09:42:00Z_
_Verifier: Claude (gsd-verifier)_
