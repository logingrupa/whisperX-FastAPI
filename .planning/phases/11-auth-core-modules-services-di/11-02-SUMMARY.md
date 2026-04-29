---
phase: 11-auth-core-modules-services-di
plan: 02
subsystem: auth
tags: [auth, core, pure-logic, tdd, argon2, jwt, api-key, csrf, device-fingerprint, rate-limit]

# Dependency graph
requires:
  - phase: 11-auth-core-modules-services-di/11-01
    provides: argon2-cffi + pyjwt installed, AuthSettings, shared _sha256_hex helper, 9 typed auth exceptions
provides:
  - app/core/password_hasher.py — Argon2id hash() + verify() (m=19456, t=2, p=1)
  - app/core/jwt_codec.py — encode_session() + decode_session() (single jwt.decode/jwt.encode site in app/)
  - app/core/api_key.py — generate() + verify() + parse_prefix() (whsk_<8>_<22> = 36 chars)
  - app/core/csrf.py — generate() + verify() (double-submit, secrets.compare_digest)
  - app/core/device_fingerprint.py — compute() (cookie/UA SHA-256 + IPv4 /24 + IPv6 /64 subnet)
  - app/core/rate_limit.py — BucketState TypedDict + consume() (pure token bucket math)
  - 28 unit tests across 6 test files in tests/unit/core/
affects:
  - 11-03 will not implement these — already done here. 11-03 in plan structure originally targeted csrf+device_fingerprint+rate_limit; this plan absorbed all 6 modules per 11-02 scope.
  - 11-04 services layer will compose: PasswordService(password_hasher), TokenService(jwt_codec, secret), KeyService(api_key, repo), CsrfService(csrf), RateLimitService(rate_limit, repo)
  - 11-05 DI container will wire TokenService(secret=Settings().auth.JWT_SECRET.get_secret_value()) and pass-through stateless services
  - 13-* HTTP routes consume decode_session via TokenService; CSRF middleware uses csrf.verify; DualAuthMiddleware uses api_key.parse_prefix + verify

# Tech tracking
tech-stack:
  added:
    - argon2.PasswordHasher (instantiated once at module load with locked OWASP params)
    - jwt.encode / jwt.decode (single-site lockdown — only app/core/jwt_codec.py)
    - ipaddress stdlib (IPv4/IPv6 subnet masking)
    - secrets.token_urlsafe (CSRF token generation, API key body+prefix entropy)
    - typing.TypedDict (BucketState shape lock)
  patterns:
    - "Tiger-style module-load asserts on every locked constant (Argon2 params, JWT algorithm, API key length, CSRF token bytes, IP prefix lengths)"
    - "PHC-string Argon2id verify with both VerifyMismatchError + InvalidHashError caught -> False (no exception leak on malformed input)"
    - "Single jwt.decode/jwt.encode call site enforced by grep — verifier rejects any sibling occurrence"
    - "DRY: _sha256_hex imported from app.core._hashing (Wave-1 helper) in api_key.py + device_fingerprint.py"
    - "RFC 7519 §4.1.2 compliance: sub claim serialized as str(user_id) — PyJWT 2.x enforces, callers recover int via int(payload['sub'])"
    - "Pure-function rate limit: now+rate+capacity all parameters; clock-skew negative elapsed clamped to 0; refill caps at capacity"
    - "Per-module RED -> GREEN TDD cycle: import-error test commit, then implementation commit (one feat per module)"

key-files:
  created:
    - app/core/password_hasher.py — Argon2id hash() + verify(); 43 LOC
    - app/core/jwt_codec.py — encode_session() + decode_session() with typed-exception mapping; 60 LOC
    - app/core/api_key.py — generate() + verify() + parse_prefix() for whsk_<8>_<22>; 55 LOC
    - app/core/csrf.py — generate() + verify() double-submit; 26 LOC
    - app/core/device_fingerprint.py — compute() pure function; 43 LOC
    - app/core/rate_limit.py — BucketState + consume() pure token bucket math; 51 LOC
    - tests/unit/core/test_password_hasher.py — 5 tests
    - tests/unit/core/test_jwt_codec.py — 5 tests (HS256 round-trip, alg=none, tampered, expired, wrong-secret)
    - tests/unit/core/test_api_key.py — 5 tests (format, verify-true, verify-false, parse round-trip, malformed-rejected)
    - tests/unit/core/test_csrf.py — 4 tests (generate, match, mismatch, empty-string)
    - tests/unit/core/test_device_fingerprint.py — 4 tests (4-key dict, 64-hex hashes, IPv4 /24, IPv6 /64)
    - tests/unit/core/test_rate_limit.py — 5 tests (within-budget, over-budget, refill cap, clock-skew, zero-tokens)
  modified: []

key-decisions:
  - "JWT sub claim serialized as str(user_id): PyJWT 2.12.1 enforces RFC 7519 §4.1.2 ('sub MUST be a case-sensitive string'). Plan body had `\"sub\": user_id` (int) which raised InvalidTokenError in round-trip. Rule 1 fix — implementation now does `\"sub\": str(user_id)` and the test asserts `payload[\"sub\"] == \"42\"` with `int(payload[\"sub\"]) == 42` documented as the caller-side recovery. Inline docstring on encode_session documents this RFC contract."
  - "rate_limit.consume on rejection still bumps last_refill to now: keeps refill clock honest while preserving tokens — when rate=0 the refill is a no-op so tokens are unchanged (matches test asserting tokens stay at 1 after over-budget rejection). Inline docstring documents this."
  - "csrf.verify short-circuits on empty-string before secrets.compare_digest: both inputs must be non-empty truthy strings. Avoids passing empty strings to compare_digest (which would still return False but loses the explicit empty-string semantics)."
  - "device_fingerprint splits compute() and _ip_subnet(): SRP — compute() composes the dict; _ip_subnet() handles IPv4/IPv6 dispatch via single isinstance check + early-return (no nested if)."
  - "api_key prefix derivation via secrets.token_urlsafe(8)[:8]: PATTERNS.md note acknowledged this may include `-` or `_` chars; that's fine for indexed string-equality lookup against a String(8) column."

patterns-established:
  - "Per-module RED→GREEN commit pairs: `test(11-02): RED - tests for <module>` followed by `feat(11-02): GREEN - implement <module>`. 6 such pairs in this plan. Each RED commit fails with ImportError (proof module doesn't exist); each GREEN commit makes its tests pass."
  - "PyJWT 2.x boundary: any code that goes through jwt_codec must accept that `sub` is a string on the wire. Wave-3 services and routes that need int user_id must call `int(payload['sub'])`."
  - "Verifier-enforced single-site discipline: `grep -rn 'jwt.decode(' app/` returns exactly 1 actual call site (line 54 of jwt_codec.py). Any future code that calls jwt.decode directly will be rejected by the verifier."

requirements-completed: [AUTH-02, AUTH-08, KEY-02, KEY-03, ANTI-03]

# Metrics
duration: 9m
completed: 2026-04-29
---

# Phase 11 Plan 02: Six pure-logic core modules + unit tests Summary

**6 pure-logic auth core modules — password_hasher (Argon2id), jwt_codec (single jwt.decode site), api_key (whsk_<8>_<22>), csrf (double-submit), device_fingerprint (SHA-256 + IP subnet), rate_limit (pure token bucket) — built test-first with 28 passing unit tests and verifier-grade single-site lockdowns on jwt.decode/jwt.encode and DRY _sha256_hex.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-04-29T05:48:45Z
- **Completed:** 2026-04-29T05:58:10Z
- **Tasks:** 2 / 2 (Task 1: 6 modules; Task 2: 6 test files — executed as 6 RED→GREEN cycles)
- **Files created:** 12 (6 core modules + 6 unit-test files)
- **Files modified:** 0
- **Commits:** 12 (6 RED `test(...)` + 6 GREEN `feat(...)`)

## Accomplishments

### Module 1 — `app/core/password_hasher.py`
- Argon2id wrapper with locked OWASP params (`m=19456`, `t=2`, `p=1`).
- `PasswordHasher` instantiated once at module load (DRY/perf).
- `verify()` catches `VerifyMismatchError` + `InvalidHashError` → `False` (no exception leak on malformed hashes per CONTEXT §115).
- 5 unit tests pass: PHC-string output, round-trip, wrong-password, malformed-hash, salt randomness.

### Module 2 — `app/core/jwt_codec.py`
- HS256-only `encode_session(*, user_id, token_version, secret, ttl_days=7)` + `decode_session(token, *, secret)`.
- **THE ONLY `jwt.decode(...)` call site in `app/`** (verified by grep).
- Maps PyJWT exceptions to typed app exceptions: `ExpiredSignatureError → JwtExpiredError`, `InvalidAlgorithmError → JwtAlgorithmError`, `InvalidTokenError → JwtTamperedError`.
- Module-load asserts on `_ALGORITHM == "HS256"` and `_METHOD == "session"`.
- 5 unit tests pass: round-trip, alg=none rejected, tampered rejected, expired rejected, wrong-secret rejected.

### Module 3 — `app/core/api_key.py`
- `generate()` returns `(plaintext, prefix, sha256_hex)` where plaintext is `whsk_<8>_<22>` (36 chars total).
- `verify()` uses `secrets.compare_digest` on SHA-256 hex (constant-time).
- `parse_prefix()` raises `InvalidApiKeyFormatError` on missing `whsk_` prefix or wrong total length.
- DRY: imports `_sha256_hex` from `app.core._hashing` (single source).
- Module-load asserts on `_TOTAL_LENGTH==36`, `_PREFIX_LENGTH==8`, `_BODY_LENGTH==22`, `_KEY_PREFIX=="whsk_"`.
- 5 unit tests pass.

### Module 4 — `app/core/csrf.py`
- `generate()`: 32 random bytes urlsafe-base64-encoded.
- `verify()`: empty-string short-circuit → `False`, else `secrets.compare_digest`.
- Module-load assert on `_TOKEN_BYTES==32`.
- 4 unit tests pass.

### Module 5 — `app/core/device_fingerprint.py`
- `compute()` pure function: returns 4-key dict (`cookie_hash`, `ua_hash`, `ip_subnet`, `device_id`).
- IPv4 → `/24` network string, IPv6 → `/64` network string via `ipaddress` stdlib.
- DRY: imports `_sha256_hex` from `app.core._hashing` (single source).
- Module-load asserts on `_IPV4_PREFIX==24` and `_IPV6_PREFIX==64`.
- 4 unit tests pass.

### Module 6 — `app/core/rate_limit.py`
- `consume(bucket, *, tokens_needed, now, rate, capacity) -> (new_bucket, allowed)`.
- Pure function: no DB, no clock side-effect (`now` is a parameter).
- Clock-skew guard: negative elapsed → `0` (no time-travel refill).
- Refill caps at `capacity`. On rejection tokens stay (only `last_refill` bumped to `now`).
- `BucketState` TypedDict locks `{tokens: int, last_refill: datetime}`.
- Module-load assert on `_REQUIRED_KEYS` shape.
- 5 unit tests pass: within-budget, over-budget, refill-caps-at-capacity, clock-skew-zero, zero-tokens-allowed.

## Task Commits

Each module RED→GREEN pair was committed atomically:

1. **password_hasher** — `01ed656` (RED test) → `c3b07ad` (GREEN feat)
2. **jwt_codec** — `721eb7f` (RED test) → `c87923e` (GREEN feat + Rule 1 RFC fix)
3. **api_key** — `6a3ade5` (RED test) → `3ec1ffc` (GREEN feat)
4. **csrf** — `2f6ec49` (RED test) → `4bbc362` (GREEN feat)
5. **device_fingerprint** — `5d446cf` (RED test) → `6fc75f0` (GREEN feat)
6. **rate_limit** — `fb811bf` (RED test) → `16db725` (GREEN feat)

## Verifier-Enforced Gate Results

| Gate | Expected | Actual | Pass |
|------|----------|--------|------|
| `pytest tests/unit/core/test_{password_hasher,jwt_codec,api_key,csrf,device_fingerprint,rate_limit}.py -q` | 27+ passed | 28 passed | yes |
| Real `jwt.decode(` call sites in app/ | exactly 1 | 1 (jwt_codec.py:54) | yes |
| Real `jwt.encode(` call sites in app/ | exactly 1 | 1 (jwt_codec.py:45) | yes |
| `from app.core._hashing import _sha256_hex` in app/core/api_key.py | 1 | 1 | yes |
| `from app.core._hashing import _sha256_hex` in app/core/csrf.py | 0 | 0 | yes |
| `from app.core._hashing import _sha256_hex` in app/core/device_fingerprint.py | 1 | 1 | yes |
| `secrets.compare_digest` in api_key.py + csrf.py | ≥2 (1 each) | 2 calls + 2 docstring mentions | yes |
| Nested-if-in-if (`^\s+if .*\bif\b`) across 6 modules | 0 | 0 | yes |
| Module-load asserts per module | ≥1 | 3+2+4+1+2+1 = 13 | yes |
| `python -c "import app.core.{module}"` for each of 6 modules | exit 0 | exit 0 (all 6) | yes |

## Decisions Made

- **JWT `sub` claim serialized as `str(user_id)`**: PyJWT 2.12.1 enforces RFC 7519 §4.1.2 ("sub MUST be a case-sensitive string"). The plan body specified `"sub": user_id` (int) which fails. Rule 1 fix — see Deviations §1.
- **`rate_limit.consume` on rejection bumps `last_refill` but preserves tokens**: when `rate=0` the refill is a no-op so tokens stay unchanged across rejected calls (matches the test asserting `bucket["tokens"]==1` after a 10-tokens-needed call against a 1-token bucket). Documented inline.
- **csrf.verify short-circuits on empty inputs** before reaching `secrets.compare_digest`: explicit `if not cookie_token or not header_token: return False` makes the empty-string semantics legible.
- **`device_fingerprint._ip_subnet` is a separate helper**: keeps `compute()` flat (single dict literal) and the IPv4/IPv6 dispatch isolated as one isinstance + early-return (no nested if).
- **api_key prefix from `secrets.token_urlsafe(8)[:8]`**: may include `-` or `_` characters per urlsafe-base64 alphabet; that is fine for indexed string-equality lookup against the `String(8)` column from Phase 10 (PATTERNS.md §344 explicitly notes this).
- **Module-level docstrings cite CONTEXT line ranges**: every module's docstring points to the locked-decision section in CONTEXT.md (e.g. `§52-60`, `§62-71`). Future maintainers can trace any constant back to its locked source.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PyJWT 2.x rejects integer `sub` claim per RFC 7519 §4.1.2**

- **Found during:** Module 2 (jwt_codec) GREEN test run — `test_encode_then_decode_round_trip` failed with `JwtTamperedError: Subject must be a string`.
- **Issue:** The plan's `<behavior>` and PATTERNS skeleton both specified `"sub": user_id` (int) inside `encode_session`. PyJWT 2.12.1 (installed in 11-01) enforces RFC 7519 §4.1.2 which states "The 'sub' value is a case-sensitive string". The decode path therefore rejected the int-typed sub claim with `InvalidTokenError`, which `jwt_codec` correctly mapped to `JwtTamperedError`. Bug is in the spec, not the implementation.
- **Fix:**
  1. `app/core/jwt_codec.py`: changed `"sub": user_id` to `"sub": str(user_id)` in `encode_session`. Added inline docstring noting the RFC contract: `"Note: per RFC 7519 §4.1.2 the sub claim MUST be a case-sensitive string; PyJWT 2.x enforces this. We serialize user_id as str(user_id) on the wire. Callers of decode_session recover the int via int(payload['sub'])."`
  2. `tests/unit/core/test_jwt_codec.py`: updated `test_encode_then_decode_round_trip` to assert `payload["sub"] == "42"` and `int(payload["sub"]) == 42` (documents the caller-side recovery). Updated `test_decode_alg_none_token_is_rejected` and `test_decode_expired_token_is_rejected` to use `"sub": "1"` instead of `"sub": 1` (otherwise the RFC-violation error mask the algorithm/expiry assertions).
- **Files modified:** `app/core/jwt_codec.py`, `tests/unit/core/test_jwt_codec.py`
- **Verification:** `pytest tests/unit/core/test_jwt_codec.py -q` → 5 passed.
- **Committed in:** `c87923e` (Module 2 GREEN commit)
- **Impact on Wave 3+:** TokenService and any future route handler that needs the integer user_id MUST call `int(payload["sub"])`. The existing `<interfaces>` documentation for jwt_codec now reflects this contract.

---

**Total deviations:** 1 auto-fixed (1 bug — RFC compliance)
**Impact on plan:** Single fix is correctness-required (RFC 7519 conformance + library-level enforcement). No scope creep — fix stays within the plan's 6-modules + 6-tests boundary, and the contract is documented for downstream consumers.

## Issues Encountered

- **Pre-existing modifications to `README.md`, `app/docs/db_schema.md`, `app/docs/openapi.json`, `app/docs/openapi.yaml`, `app/main.py`, `frontend/src/components/upload/FileQueueItem.tsx`** in working tree at plan start — completely unrelated to this plan's auth core work. Out of scope. Not committed by this plan. Logged as pre-existing.
- **Untracked `app/core/auth.py` and `models/`** at plan start — pre-existing untracked files (`auth.py` is the existing bearer-token middleware referenced for `secrets.compare_digest` analog; `models/` is the local model cache directory). Out of scope. Not committed by this plan.
- **PyJWT `InsecureKeyLengthWarning`** in 4 jwt_codec tests: HMAC key shorter than 32 bytes (test secrets are intentionally short for fixture brevity). Warning only, not a failure. Test fixtures are appropriate scope; production secret length is enforced separately by AuthSettings + production-safety validator from 11-01.

## Threat Flags

None — all changes stay within the plan's documented threat model. T-11-04 (HS256-only single decode site), T-11-05 (constant-time compare in api_key + csrf), T-11-06 (clock-skew clamp in rate_limit), T-11-07 (Argon2 verify timing — accepted, library-handled), T-11-08 (Argon2 cost params asserted at module load) all delivered as specified.

## User Setup Required

None — these are pure-logic modules with no external dependencies beyond the libraries installed in 11-01 (argon2-cffi 25.1.0, pyjwt 2.12.1).

## Next Phase Readiness

Wave 3 (services + repositories) and the originally-planned 11-03 plan can now proceed:

- **11-03 (originally csrf + device_fingerprint + rate_limit):** All 3 modules already implemented in this plan. 11-03 is effectively a no-op for module creation; if any tasks remain in 11-03 (e.g. additional integration prep), they consume what's here.
- **11-04 (services):** can compose `password_hasher.{hash,verify}`, `jwt_codec.{encode_session,decode_session}`, `api_key.{generate,verify,parse_prefix}`, `csrf.{generate,verify}`, `device_fingerprint.compute`, `rate_limit.consume` directly. All 6 modules are stateless function-style (rate_limit + device_fingerprint compute on inputs only); password_hasher caches one PasswordHasher instance at module load; jwt_codec is pure functions taking secret as parameter (DI-friendly).
- **11-05 (DI):** `TokenService(secret=Settings().auth.JWT_SECRET.get_secret_value())` will resolve correctly (secret from AuthSettings); stateless services (`PasswordService`, `CsrfService`) become `providers.Singleton`.
- **13-* HTTP routes:** `decode_session` is the single ingress for JWT validation; `csrf.verify` is the single ingress for double-submit CSRF; `api_key.parse_prefix` + `verify` is the indexed-lookup path for DualAuthMiddleware. Verifier guarantees no other site decodes JWTs or compares CSRF tokens unsafely.

No blockers for Wave 3.

## Self-Check: PASSED

Verified after SUMMARY write:

- `app/core/password_hasher.py` — FOUND
- `app/core/jwt_codec.py` — FOUND
- `app/core/api_key.py` — FOUND
- `app/core/csrf.py` — FOUND
- `app/core/device_fingerprint.py` — FOUND
- `app/core/rate_limit.py` — FOUND
- `tests/unit/core/test_password_hasher.py` — FOUND
- `tests/unit/core/test_jwt_codec.py` — FOUND
- `tests/unit/core/test_api_key.py` — FOUND
- `tests/unit/core/test_csrf.py` — FOUND
- `tests/unit/core/test_device_fingerprint.py` — FOUND
- `tests/unit/core/test_rate_limit.py` — FOUND
- Commit `01ed656` (test password_hasher) — FOUND
- Commit `c3b07ad` (feat password_hasher) — FOUND
- Commit `721eb7f` (test jwt_codec) — FOUND
- Commit `c87923e` (feat jwt_codec) — FOUND
- Commit `6a3ade5` (test api_key) — FOUND
- Commit `3ec1ffc` (feat api_key) — FOUND
- Commit `2f6ec49` (test csrf) — FOUND
- Commit `4bbc362` (feat csrf) — FOUND
- Commit `5d446cf` (test device_fingerprint) — FOUND
- Commit `6fc75f0` (feat device_fingerprint) — FOUND
- Commit `fb811bf` (test rate_limit) — FOUND
- Commit `16db725` (feat rate_limit) — FOUND

## TDD Gate Compliance

- RED gate (`test(...)` commit) precedes GREEN gate (`feat(...)` commit) for all 6 modules — verified via `git log --oneline | grep "(11-02)"`.
- No RED tests passed unexpectedly: each RED commit's tests fail with `ImportError: cannot import name '<module>' from 'app.core'` — verified at RED commit time.
- No REFACTOR commits made (none needed; docstring tweak in rate_limit was rolled into its initial GREEN commit).

---
*Phase: 11-auth-core-modules-services-di*
*Completed: 2026-04-29*
