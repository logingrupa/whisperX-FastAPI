# Phase 11: Auth Core Modules + Services + DI - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Pure-logic auth/key/rate-limit/CSRF modules and services exist with single-source-of-truth invariants and pass unit tests. **Not yet wired into any HTTP route** — that's Phase 13's job.

In scope:
- Pure-logic core modules (one per concern):
  - `app/core/password_hasher.py` — Argon2id `hash(plain) -> str`, `verify(plain, hashed) -> bool`
  - `app/core/jwt_codec.py` — single source of `jwt.decode()`/`jwt.encode()`; `encode_session()`, `decode_session()`; `algorithms=["HS256"]` always
  - `app/core/api_key.py` — `generate() -> (plaintext, prefix, hash)`; `verify(plaintext, stored_hash)` via `secrets.compare_digest`; `parse_prefix(plaintext)`
  - `app/core/csrf.py` — double-submit token: `generate() -> str`, `verify(cookie_token, header_token) -> bool` via `secrets.compare_digest`
  - `app/core/device_fingerprint.py` — `compute(cookie_value, user_agent, client_ip, device_id) -> dict[str, str]` (returns hashes + ip_subnet)
  - `app/core/rate_limit.py` — pure-logic token bucket math: `consume(bucket_state, tokens, now, rate, capacity) -> (new_state, allowed)`
- Services (orchestration on top of core modules) in `app/services/auth/`:
  - `password_service.py` — wraps password_hasher; verifies user password against stored hash; raises typed exceptions
  - `token_service.py` — wraps jwt_codec; issues session tokens; refreshes on activity
  - `auth_service.py` — registers user (with password_service + repos); logs in (verifies password, issues token via token_service); logs out (clears session)
  - `key_service.py` — creates API key (api_key.generate + persist hash); verifies + rate-limits
  - `rate_limit_service.py` — uses rate_limit core; persists bucket state via repo
  - `csrf_service.py` — issues CSRF tokens; verifies double-submit
- New repositories needed for the services:
  - `IUserRepository` + `SqlAlchemyUserRepository`
  - `IApiKeyRepository` + `SqlAlchemyApiKeyRepository`
  - `IRateLimitRepository` + `SqlAlchemyRateLimitRepository`
  - `IDeviceFingerprintRepository` + `SqlAlchemyDeviceFingerprintRepository`
  - (Subscription/UsageEvent repos deferred to Phase 13/15 — not needed for unit tests in this phase)
- Domain entities (mirror ORM, framework-free): `User`, `ApiKey`, `RateLimitBucket`, `DeviceFingerprint` in `app/domain/entities/`
- DI Container providers added in `app/core/container.py` for: `password_service`, `token_service`, `auth_service`, `key_service`, `rate_limit_service`, `csrf_service` (all factories where stateful, singletons where pure)
- Unit tests in `tests/unit/core/` for core modules + `tests/unit/services/auth/` for services
- CI Argon2 benchmark test `tests/integration/test_argon2_benchmark.py` asserting <300ms p99 over 100 hashes

Out of scope (explicit deferrals, owned by later phases):
- HTTP routes (DualAuthMiddleware, /auth/login, /auth/register, /api/keys, etc.) → Phase 13
- WebSocket ticket flow → Phase 13
- Free-tier gates / 401/403/429 responses → Phase 13
- Stripe checkout/webhook stubs → Phase 13
- Account deletion / logout-all-devices → Phase 15
- Frontend auth shell → Phase 14
- Migration runbook / .env.example documentation → Phase 17

</domain>

<decisions>
## Implementation Decisions

### Argon2 Parameters (locked from STATE.md / REQUIREMENTS.md AUTH-02)

- Algorithm: Argon2id
- Memory cost: `m=19456 KiB` (≈19 MB)
- Time cost: `t=2`
- Parallelism: `p=1`
- Library: `argon2-cffi` (battle-tested OWASP-recommended impl)
- Hash format: PHC-string standard (`$argon2id$v=19$m=19456,t=2,p=1$<salt>$<hash>`)
- Verify must be constant-time (library handles internally)

### JWT (locked from REQUIREMENTS.md AUTH-08)

- Algorithm: HS256 ONLY — single decode site `app/core/jwt_codec.py`
- Library: `PyJWT` (pyjwt) — already standard for FastAPI
- Decode invocation: `jwt.decode(token, secret, algorithms=["HS256"])` — never `algorithms=None` or list with `none`
- Token shape: `{"sub": user_id, "iat": now, "exp": now+7d, "ver": user.token_version, "method": "session"}`
- Sliding expiry handled by token_service (issues new token on every authenticated request)
- Secret: `JWT_SECRET` env var (Pydantic Settings); fail loudly if unset in production
- `grep -rn "jwt.decode(" app/` MUST return exactly 1 match — `app/core/jwt_codec.py`

### API Key Format (locked from REQUIREMENTS.md KEY-02, KEY-03, KEY-08)

- Format: `whsk_<8charPrefix>_<22charBase64Random>` — total 36 chars
  - `whsk_` literal (5 chars)
  - 8-char base64 prefix (used for indexed lookup)
  - `_` separator (1 char)
  - 22 chars of url-safe base64 of 16 random bytes (≈128 bits entropy)
- Storage: SHA-256 hash of plaintext (hex, 64 chars) — never plaintext
- Verification: prefix lookup (uses `idx_api_keys_prefix` from Phase 10) → SHA-256 hash compare via `secrets.compare_digest`
- Generation source: `secrets.token_urlsafe(16)` for the random body; deterministic prefix derivation from the body

### Logging Hygiene (locked from REQUIREMENTS.md AUTH-09)

- All structured logs from auth services use `logger` from `app.core.logging`
- NEVER log raw passwords, JWT secrets, full API keys
- Keys may log `prefix` only (e.g. `key_id=42 prefix=abc12345`)
- JWT logs may log `sub`, `exp`, but never the raw token
- Centralized logging filter in `app.core.logging` redacts `password`, `secret`, `api_key`, `token` keys from any structured field
- Tests grep service log output for sensitive substrings — must return 0 hits

### Rate Limit Logic

- Token bucket math is **pure** in `app/core/rate_limit.py` — no DB I/O
- `consume(bucket: dict, tokens_needed: int, now: datetime, rate: float, capacity: int) -> tuple[dict, bool]`
  - Returns updated bucket (refill timestamp + token count) and allowed-flag
  - Bucket dict shape: `{"tokens": int, "last_refill": datetime}` — matches `rate_limit_buckets` table
- `rate_limit_service.py` wraps the pure logic with repo-backed persistence (`BEGIN IMMEDIATE` transaction wrapping read+update for SQLite worker-safety)
- Bucket key conventions (locked):
  - Per-user-per-hour: `user:{id}:tx:hour`
  - Per-IP-per-action: `ip:{subnet}:{action}:hour`
  - Concurrency slots: `user:{id}:concurrent`

### CSRF (double-submit cookie pattern)

- Token: 32 bytes from `secrets.token_urlsafe()`
- Issue: `generate() -> str` returns the token; caller sets it as both a cookie and ships it back to client for the header
- Verify: `verify(cookie_token: str, header_token: str) -> bool` — `secrets.compare_digest` between cookie and header
- Bearer-authenticated routes skip CSRF entirely (handled in Phase 13 middleware)

### Device Fingerprint

- Inputs: `cookie_value` (raw session cookie), `user_agent` (raw UA string), `client_ip` (str), `device_id` (UUID from localStorage — supplied by frontend)
- Outputs:
  - `cookie_hash`: SHA-256 of cookie_value (hex, 64 chars)
  - `ua_hash`: SHA-256 of user_agent (hex, 64 chars)
  - `ip_subnet`: IPv4 → `/24` masked; IPv6 → `/64` masked (string form)
  - `device_id`: passed through as-is
- Pure logic — no DB. Service wraps with repo persistence.

### DI Container

- Providers added in `app/core/container.py`:
  - `password_service = providers.Singleton(PasswordService)` — stateless
  - `token_service = providers.Singleton(TokenService, secret=config.provided.auth.JWT_SECRET)`
  - `csrf_service = providers.Singleton(CsrfService)`
  - `user_repository = providers.Factory(SqlAlchemyUserRepository, session=db_session_factory)`
  - `api_key_repository = providers.Factory(SqlAlchemyApiKeyRepository, session=db_session_factory)`
  - `rate_limit_repository = providers.Factory(SqlAlchemyRateLimitRepository, session=db_session_factory)`
  - `device_fingerprint_repository = providers.Factory(SqlAlchemyDeviceFingerprintRepository, session=db_session_factory)`
  - `auth_service = providers.Factory(AuthService, user_repository=user_repository, password_service=password_service, token_service=token_service)`
  - `key_service = providers.Factory(KeyService, repository=api_key_repository)`
  - `rate_limit_service = providers.Factory(RateLimitService, repository=rate_limit_repository)`
- All repos use the existing `db_session_factory` from Phase 10
- Acceptance: each provider resolves to a fresh instance (factories) or the same instance (singletons); structural log scan returns 0 sensitive substrings

### Settings Additions

Pydantic Settings additions in `app/core/config.py`:
- `class AuthSettings(BaseSettings)` (env_prefix `AUTH__`):
  - `JWT_SECRET: SecretStr` (required; fail loudly if missing in non-test envs)
  - `JWT_TTL_DAYS: int = 7`
  - `ARGON2_M_COST: int = 19456`
  - `ARGON2_T_COST: int = 2`
  - `ARGON2_PARALLELISM: int = 1`
  - `CSRF_SECRET: SecretStr` (required for prod; defaulted in test)

### Code Quality (locked from user)

- **DRY** — single `jwt_codec` module owns ALL `jwt.decode/jwt.encode` calls; `secrets.compare_digest` used in every constant-time compare; shared `_sha256_hex(s: str) -> str` helper for any SHA-256 hex conversion
- **SRP** — one core module per concern (no `auth_utils.py` grab bag); services orchestrate, do not contain hash logic; repos do persistence only
- **/tiger-style** — assert invariants at module load (e.g. `assert len(KEY_PREFIX_LENGTH) == 8`); `argon2-cffi` PasswordHasher instantiated once at module load with explicit params; raise typed exceptions on bad input (`InvalidApiKeyFormatError`, `InvalidJwtError`); no silent fallbacks
- **No spaghetti** — early returns; guard clauses; max 2 nesting levels; no nested-if-in-if-in-if (`grep -cE "^if .*if " app/core/*.py` returns 0)
- **Self-explanatory names** — `password_hasher`, `jwt_codec`, `api_key`, `token_service`, `rate_limit_service`; no abbreviations like `pw_svc` or `auth_util`

### Claude's Discretion

- Exception class names (recommend: `InvalidApiKeyFormatError`, `InvalidApiKeyHashError`, `JwtAlgorithmError`, `JwtExpiredError`, `JwtTamperedError`, `WeakPasswordError`, `RateLimitExceededError`)
- Whether to put repos in `app/infrastructure/database/repositories/` (matches existing `sqlalchemy_task_repository.py`) — yes, this is the established pattern
- Whether to put auth services in `app/services/auth/` package or flat `app/services/auth_service.py` etc. — package preferred for namespace cleanliness
- Test file layout: `tests/unit/core/test_<module>.py` and `tests/unit/services/auth/test_<service>.py` — one file per module
- Whether to expose CSRF/device fingerprint helpers via `__init__.py` re-exports — yes, slim public surface

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/core/container.py` — extend with new providers; existing `db_session_factory`/`task_repository` patterns are direct analogs
- `app/core/config.py` — extend with `AuthSettings` (Pydantic Settings nested class)
- `app/core/exceptions.py` — extend with new typed exceptions (auth-specific subclasses of `DomainError`/`ValidationError`)
- `app/core/logging.py` — extend with redaction filter for sensitive keys
- `app/infrastructure/database/models.py` — User/ApiKey/RateLimitBucket/DeviceFingerprint ORM classes already exist (Phase 10)
- `app/infrastructure/database/repositories/sqlalchemy_task_repository.py` — analog for new repository implementations
- `app/domain/repositories/task_repository.py` — analog for new `Protocol`-based repository interfaces
- `app/domain/entities/task.py` — analog for new domain entities

### Established Patterns

- Snake_case modules, PascalCase classes, snake_case columns
- `Protocol`-based repository interfaces in `app/domain/repositories/`
- SQLAlchemy 2.x `Mapped[T]` + `mapped_column(...)` style
- Pydantic Settings via `app.core.config.Config` — already used by Alembic env.py
- Logging via `app.core.logging.logger` — never `logging.basicConfig()`
- Errors via `app.core.exceptions` typed exception hierarchy
- `dependency-injector` Container providers (Singleton vs Factory based on statefulness)
- pytest markers: `@pytest.mark.unit` for fast tests, `@pytest.mark.integration` for DB-touching

### Integration Points

- `app/core/container.py` — add new providers after existing service providers
- `app/core/config.py` — add `AuthSettings` nested settings class
- `app/core/exceptions.py` — add auth-specific exception classes
- `app/core/logging.py` — wire redaction filter into existing logger
- `app/core/__init__.py` — re-export new core modules' public surface (slim, e.g. `from .password_hasher import hash, verify`)
- `app/services/__init__.py` — re-export new service classes
- `app/domain/entities/__init__.py` — re-export new entities
- `app/domain/repositories/__init__.py` — re-export new repository interfaces
- `pyproject.toml` — add `argon2-cffi` and `pyjwt` dependencies

</code_context>

<specifics>
## Specific Ideas

- The `jwt_codec.py` MUST be the only module importing `jwt.decode`. The verifier will grep for `jwt.decode(` across `app/` and reject any match outside `app/core/jwt_codec.py`.
- `argon2-cffi` exposes `argon2.PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)` — instantiate once at module load.
- The Argon2 benchmark test runs the deploy-target hardware profile (best-effort: 100 hashes, p99 < 300ms). On low-end CI it may be flaky — mark it `@pytest.mark.slow` and gate via `pytest -m "slow"` in CI but not in default local runs.
- API key plaintext is shown to the user **once** at creation time (Phase 13's `/api/keys` POST returns it once); after that only the hash + prefix exist on the server. The phase 11 `key_service.create_key()` returns the plaintext (caller — Phase 13 route handler — is responsible for showing-once UX).

</specifics>

<deferred>
## Deferred Ideas

- DualAuthMiddleware integration — Phase 13
- WebSocket ticket flow — Phase 13
- Free-tier rate limit policies (5/hr, 30min/day, etc.) — Phase 13 wiring of rate_limit_service
- hCaptcha hook scaffold — Phase 13
- Disposable email blocklist — Phase 13 wiring (data file lives in `data/disposable-emails.txt`)
- Subscription / UsageEvent repos — Phase 13 (when Stripe stubs are wired)
- Migration runbook + `.env.example` updates — Phase 17

</deferred>
