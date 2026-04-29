---
phase: 11-auth-core-modules-services-di
plan: 01
subsystem: auth
tags: [auth, foundation, settings, logging, deps, argon2, jwt, pydantic-settings]

# Dependency graph
requires:
  - phase: 10-alembic-baseline-auth-schema
    provides: Auth ORM tables (users, api_keys, rate_limit_buckets, device_fingerprints) ready for Wave 2 services
provides:
  - argon2-cffi 25.1.0 + pyjwt 2.12.1 declared and installed
  - AuthSettings nested settings (JWT_SECRET, JWT_TTL_DAYS, ARGON2_M/T/PARALLELISM, CSRF_SECRET) loadable via Settings().auth
  - env_prefix=AUTH__ on AuthSettings — maps AUTH__JWT_SECRET env var to settings.auth.JWT_SECRET
  - Production-safety model_validator — refuses to boot when ENVIRONMENT=production AND secrets are still dev defaults
  - Shared _sha256_hex helper (single DRY source) at app/core/_hashing.py
  - RedactingFilter wired onto whisperX logger — defense-in-depth scrub of password/secret/api_key/token in structured fields and dict args
  - 9 typed auth exceptions (InvalidCredentials, UserAlreadyExists, InvalidApiKey{Format,Hash}, Jwt{Algorithm,Expired,Tampered}, WeakPassword, RateLimitExceeded)
affects:
  - 11-02 password_hasher + jwt_codec + api_key core modules (import _sha256_hex, raise typed exceptions, use AuthSettings)
  - 11-03 csrf + device_fingerprint + rate_limit core modules (import _sha256_hex)
  - 11-04 services layer (uses Settings().auth.JWT_SECRET, raises typed exceptions)
  - 11-05 DI container (binds Settings().auth.JWT_SECRET to TokenService)
  - 13-* HTTP routes (relies on RedactingFilter for log hygiene, AuthSettings for runtime secrets)

# Tech tracking
tech-stack:
  added:
    - argon2-cffi>=23.1.0 (Argon2id password hashing — installed argon2-cffi 25.1.0)
    - pyjwt>=2.8.0 (JWT HS256 encode/decode — installed pyjwt 2.12.1)
  patterns:
    - "Pydantic Settings: nested config class with env_prefix + model_validator(mode='after') for production safety"
    - "Tiger-style invariants — assert at module load (app/core/_hashing.py, app/core/_log_redaction.py)"
    - "Typed auth exceptions — DomainError + ValidationError subclasses with stable codes (INVALID_CREDENTIALS, USER_ALREADY_EXISTS, etc.)"
    - "logging.Filter subclass with case-insensitive sensitive-key regex; addFilter at module-load tail (post dictConfig)"
    - "Email-elision in UserAlreadyExistsError message (anti-enumeration leak via stack traces)"

key-files:
  created:
    - app/core/_hashing.py — single source of _sha256_hex helper
    - app/core/_log_redaction.py — RedactingFilter (logging.Filter)
    - .planning/phases/11-auth-core-modules-services-di/11-01-SUMMARY.md
  modified:
    - pyproject.toml — added argon2-cffi + pyjwt to dependencies list
    - app/core/config.py — added AuthSettings + Settings.auth field; imported SecretStr
    - app/core/logging.py — addFilter(RedactingFilter()) at module-load tail with noqa: E402
    - app/core/exceptions.py — appended 9 Phase 11 auth exceptions
    - tests/unit/core/test_config.py — provide AUTH__JWT_SECRET + AUTH__CSRF_SECRET in production-env test (Rule 1 fix)

key-decisions:
  - "AuthSettings.model_config sets env_prefix='AUTH__' so AUTH__JWT_SECRET / AUTH__CSRF_SECRET env vars hydrate at instantiation time (matches CONTEXT §140 spec; required because Settings.auth is constructed via default_factory which bypasses env_nested_delimiter on the parent)"
  - "JWT_SECRET / CSRF_SECRET keep harmless dev defaults ('change-me-dev-only') — model_validator(mode='after') rejects them only when ENVIRONMENT=production. Plan note (line 234) explicitly forbids Field(...) ellipsis-required because that would break test envs"
  - "RedactingFilter import sits at the BOTTOM of app/core/logging.py with noqa: E402 — must run AFTER logging.config.dictConfig(config) which configures the named whisperX logger. Moving to the top would attach filter before logger exists"
  - "UserAlreadyExistsError takes no constructor arg — never accepts/embeds the user's email in message=. Anti-enumeration leak via stack traces or log formatters (CONTEXT §156-163; threat T-11-03)"
  - "RateLimitExceededError constructor takes positional bucket_key + retry_after_seconds; retry_after_seconds is forwarded into ApplicationError.details via **details kwarg (verifier checks .details['retry_after_seconds'])"

patterns-established:
  - "Shared crypto helper in app/core/_<name>.py — leading underscore signals 'internal infra, not public API'. Future plans (11-02 api_key, 11-03 csrf+device_fingerprint) import _sha256_hex from this module rather than duplicating hashlib calls"
  - "Module-load assertions for invariants (assert _DIGEST_HEX_LENGTH == 64, assert _REDACTED == '***REDACTED***') — fail loudly on accidental drift"
  - "Production-safety validator pattern — read os.environ inside @model_validator(mode='after'); skip check unless ENVIRONMENT=='production'; raise ValueError on dev-default match"
  - "Auth exception code naming — SCREAMING_SNAKE_CASE matching the class name verb (INVALID_CREDENTIALS, USER_ALREADY_EXISTS, JWT_EXPIRED, RATE_LIMIT_EXCEEDED)"

requirements-completed: [AUTH-09]

# Metrics
duration: 6m
completed: 2026-04-29
---

# Phase 11 Plan 01: Foundation (deps + AuthSettings + redaction + exceptions) Summary

**Auth foundation: argon2-cffi/pyjwt deps installed, AuthSettings (6 fields, env_prefix=AUTH__) with production-safety validator, single-source _sha256_hex helper, RedactingFilter wired on whisperX logger, and 9 typed auth exceptions ready for Wave 2 services.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-29T05:39:06Z
- **Completed:** 2026-04-29T05:44:49Z
- **Tasks:** 2 / 2
- **Files modified:** 4 (pyproject.toml, app/core/config.py, app/core/logging.py, app/core/exceptions.py, tests/unit/core/test_config.py)
- **Files created:** 2 (app/core/_hashing.py, app/core/_log_redaction.py)

## Accomplishments

- `argon2-cffi 25.1.0` + `pyjwt 2.12.1` installed in venv and declared in pyproject.toml dependencies list
- `AuthSettings` BaseSettings nested class with all 6 fields at locked CONTEXT §138-147 defaults (JWT_SECRET, JWT_TTL_DAYS=7, ARGON2_M_COST=19456, ARGON2_T_COST=2, ARGON2_PARALLELISM=1, CSRF_SECRET)
- `env_prefix="AUTH__"` on AuthSettings — `AUTH__JWT_SECRET=...` env var hydrates `Settings().auth.JWT_SECRET` correctly under default_factory construction
- `model_validator(mode="after")` refuses to boot in production with dev-default secrets (threat T-11-02 mitigated)
- `Settings.auth = Field(default_factory=AuthSettings)` registered immediately after `callback`
- `app/core/_hashing.py` ships `_sha256_hex(s: str) -> str` — verified to be the single match across `app/` (DRY locked per CONTEXT §150)
- `app/core/_log_redaction.py` defines `RedactingFilter(logging.Filter)` scrubbing case-insensitive `password|secret|api_key|token` keys in `record.__dict__` and dict-shaped `record.args`
- `logger.addFilter(RedactingFilter())` wired at module-load tail of `app/core/logging.py` (noqa: E402 import below dictConfig)
- 9 typed auth exceptions appended to `app/core/exceptions.py` (verbatim from PATTERNS.md §870-965 with the email-elision tweak from CONTEXT §156-163 / threat T-11-03)

## Task Commits

Each task was committed atomically:

1. **Task 1: deps + AuthSettings + _sha256_hex** — `2ceab7a` (feat)
2. **Task 2: RedactingFilter + 9 typed auth exceptions** — `8b2f4e6` (feat)

## Files Created/Modified

### Created

- `app/core/_hashing.py` — `_sha256_hex(s: str) -> str` shared helper. Module-load assert on digest hex length (64). Imported by 11-02 api_key, 11-03 csrf + device_fingerprint
- `app/core/_log_redaction.py` — `RedactingFilter(logging.Filter)` scrubs `password|secret|api_key|token` from structured fields. Module-load assert on `_REDACTED == "***REDACTED***"`

### Modified

- `pyproject.toml` — appended `argon2-cffi>=23.1.0` and `pyjwt>=2.8.0` to `dependencies = [...]`
- `app/core/config.py` —
  - line 7: import added `SecretStr` alongside `Field, computed_field, field_validator, model_validator`
  - lines 136-180: new `AuthSettings(BaseSettings)` class with `model_config = SettingsConfigDict(env_prefix="AUTH__", env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore")` and `_reject_dev_defaults_in_production` validator
  - line 169 (post-`callback` registration): `auth: AuthSettings = Field(default_factory=AuthSettings)` on `class Settings`
- `app/core/logging.py` — append after `logger.debug(f"Debug messages enabled: {debug}")`: import + `logger.addFilter(RedactingFilter())` with noqa: E402 marker explaining post-dictConfig ordering
- `app/core/exceptions.py` — append after `MissingConfigurationError`: 9 auth exception classes
- `tests/unit/core/test_config.py` — `TestSettings.test_default_values` env patch now also sets `AUTH__JWT_SECRET` + `AUTH__CSRF_SECRET` since the test forces `ENVIRONMENT=production` (would otherwise trip the new production-safety validator)

## Decisions Made

- **env_prefix on AuthSettings:** Plan/PATTERNS map called for env_prefix="AUTH__" (CONTEXT §140); confirmed this is required — `default_factory=AuthSettings` constructs the nested settings standalone (NOT through Settings' env_nested_delimiter), so without env_prefix the AUTH__JWT_SECRET env var would never reach the nested fields and the production-safety validator would always raise. Added `model_config = SettingsConfigDict(env_prefix="AUTH__", ...)` block to the class.
- **Production-safety validator:** Reads `os.environ.get("ENVIRONMENT", "")` directly (NOT `self.ENVIRONMENT` — AuthSettings is nested and has no ENVIRONMENT field). Skips the assertion in dev/test envs by returning early. Production (ENVIRONMENT=production) raises `ValueError` on dev-default secret values.
- **UserAlreadyExistsError signature:** Plan (line 449) forbids embedding email in `message=`. Constructor takes NO arguments — message is hardcoded `"User with email already exists"`. Prevents enumeration leak via tracebacks/log formatters.
- **Exception code stability:** Codes lifted verbatim from PATTERNS.md §870-965 — these become the contract that 11-02/11-03 services raise and that 13-* HTTP routes map to status codes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AuthSettings env_prefix needed for nested default_factory**
- **Found during:** Task 1 verification (`pytest tests/unit/core/test_config.py::TestSettings::test_default_values` failed)
- **Issue:** Plan specified `class AuthSettings(BaseSettings)` body but did not add a `model_config = SettingsConfigDict(env_prefix="AUTH__", ...)` block. Because `Settings.auth = Field(default_factory=AuthSettings)` constructs the nested settings via the factory function (NOT via Settings' `env_nested_delimiter="__"` mechanism), the `AUTH__JWT_SECRET` env var was not reaching `AuthSettings.JWT_SECRET`. With `ENVIRONMENT=production`, the production-safety validator therefore always tripped on the dev default — including in the existing pytest case that explicitly sets `ENVIRONMENT=production`.
- **Fix:** Added explicit `model_config = SettingsConfigDict(env_prefix="AUTH__", env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore")` to AuthSettings. Matches the locked CONTEXT §140 spec ("env_prefix `AUTH__`") which the plan body had elided.
- **Files modified:** `app/core/config.py`
- **Verification:** All 15 tests in `tests/unit/core/test_config.py` pass; `Settings()` resolves with all 6 auth fields at locked defaults in non-prod envs; `python -c "from app.core.config import Settings; print(Settings().auth.ARGON2_M_COST)"` prints `19456`.
- **Committed in:** `2ceab7a` (Task 1 commit)

**2. [Rule 1 - Bug] test_config.py test_default_values needed AUTH secrets**
- **Found during:** Task 1 verification (post env_prefix fix above)
- **Issue:** `TestSettings::test_default_values` patches the environment with `ENVIRONMENT=production` to test that production-mode Settings instantiate cleanly with default values for everything else. The new AuthSettings production-safety validator (intentionally) refuses to boot in production with `change-me-dev-only` secrets — this is correctness-required behavior (threat T-11-02), so the right fix is to make the test honor the new contract by also setting `AUTH__JWT_SECRET` and `AUTH__CSRF_SECRET` env vars.
- **Fix:** Added two new keys to the test's `patch.dict(os.environ, ...)` block: `"AUTH__JWT_SECRET": "test-jwt-secret-not-the-default"`, `"AUTH__CSRF_SECRET": "test-csrf-secret-not-the-default"`. Inline comment explains the linkage to AuthSettings._reject_dev_defaults_in_production.
- **Files modified:** `tests/unit/core/test_config.py`
- **Verification:** `pytest tests/unit/core/test_config.py -q` → 15 passed.
- **Committed in:** `2ceab7a` (Task 1 commit, alongside the env_prefix fix)

**3. [Rule 3 - Blocking] Installed argon2-cffi + pyjwt into venv**
- **Found during:** Task 1 verification (success criterion: "argon2-cffi and pyjwt installed and importable")
- **Issue:** Adding to pyproject.toml only declares the dependency; the venv was missing the actual packages, so `import argon2; import jwt` raised `ModuleNotFoundError`. Wave 2 plans cannot run their unit tests until these are physically present.
- **Fix:** `python -m pip install "argon2-cffi>=23.1.0" "pyjwt>=2.8.0"` into the project venv (`.venv/Scripts/python.exe`). Resolved to argon2-cffi 25.1.0 + pyjwt 2.12.1 + argon2-cffi-bindings 25.1.0.
- **Files modified:** None (pip-managed venv state, not tracked in git)
- **Verification:** `python -c "import argon2; import jwt; print('argon2 ok'); print('jwt ok')"` → both ok.
- **Committed in:** N/A (venv install only; pyproject.toml change committed in `2ceab7a`)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All three fixes are correctness-required: deviations 1+2 unblock the plan's stated verify command and acceptance criteria; deviation 3 satisfies a literal success criterion. No scope creep — every fix stays within the plan's 4-file modify + 2-file create boundary.

## Issues Encountered

- Pre-existing `tests/unit/services/test_audio_processing_service.py` failures (4 tests asserting `update` called once but service emits 4 progress-stage updates) — completely unrelated to this plan's auth foundation work. Logged as out-of-scope.
- Pre-existing test collection errors in `tests/unit/domain/entities/test_task.py`, `tests/unit/infrastructure/database/{mappers,repositories}/test_*.py` due to missing `factory_boy` (declared as dev optional dependency, not installed in venv) — out of scope.

## Threat Flags

None — all changes stay within the plan's documented threat model. T-11-01 (RedactingFilter) and T-11-02 (production-safety AuthSettings validator) and T-11-03 (no email in UserAlreadyExistsError) all delivered as specified.

## User Setup Required

None — no external service configuration required. AuthSettings ships with safe dev defaults and refuses to boot in production until secrets are explicitly set via env vars (`AUTH__JWT_SECRET=...` and `AUTH__CSRF_SECRET=...`). Phase 17 is responsible for production env runbook.

## Next Phase Readiness

Wave 2 (Plans 11-02 and 11-03) can now run in parallel against this stable surface:

- **11-02** (`password_hasher`, `jwt_codec`, `api_key`): `from argon2 import PasswordHasher` works; `import jwt` works; `from app.core._hashing import _sha256_hex` works (DRY); `Settings().auth.JWT_SECRET.get_secret_value()` resolves; `from app.core.exceptions import InvalidApiKeyFormatError, JwtAlgorithmError, JwtExpiredError, JwtTamperedError` works.
- **11-03** (`csrf`, `device_fingerprint`, `rate_limit`): `from app.core._hashing import _sha256_hex` works (single DRY source); `from app.core.exceptions import RateLimitExceededError` works.
- **11-04** (services): `Settings().auth` is fully populated; all 9 typed exceptions importable; `logger.filters` already includes `RedactingFilter` (defense-in-depth net for any logger.info(...) calls in service code).
- **11-05** (DI): `config.provided.auth.JWT_SECRET` will resolve (mirroring the existing `config.provided.whisper.HF_TOKEN` pattern in container.py).

No blockers for Wave 2. Foundation gate is GREEN.

## Self-Check: PASSED

Verified after SUMMARY write:

- `app/core/_hashing.py` — FOUND
- `app/core/_log_redaction.py` — FOUND
- `app/core/config.py` (modified) — FOUND with `class AuthSettings` + `auth: AuthSettings`
- `app/core/logging.py` (modified) — FOUND with `logger.addFilter(RedactingFilter())`
- `app/core/exceptions.py` (modified) — FOUND with all 9 new auth exceptions
- `pyproject.toml` (modified) — FOUND with `argon2-cffi` + `pyjwt`
- `tests/unit/core/test_config.py` (modified) — FOUND with AUTH secret env patches
- Commit `2ceab7a` — FOUND in `git log`
- Commit `8b2f4e6` — FOUND in `git log`

---
*Phase: 11-auth-core-modules-services-di*
*Completed: 2026-04-29*
