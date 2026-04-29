# Phase 11: Auth Core Modules + Services + DI - Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 47 (33 NEW + 5 MODIFY + 13 NEW tests)
**Analogs found:** 47 / 47

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/core/password_hasher.py` | utility/core | transform | `app/core/auth.py` (constant-time compare via `secrets.compare_digest`) | partial — no Argon2 analog yet |
| `app/core/jwt_codec.py` | utility/core | transform | `app/core/auth.py` (token verify) | partial — no JWT analog yet |
| `app/core/api_key.py` | utility/core | transform | `app/core/auth.py` (`secrets.compare_digest` pattern) | partial |
| `app/core/csrf.py` | utility/core | transform | `app/core/auth.py` (`secrets.compare_digest`) | partial |
| `app/core/device_fingerprint.py` | utility/core | transform | `app/services/file_service.py` (stateless static utils) | role-match |
| `app/core/rate_limit.py` | utility/core | transform (pure function) | `app/services/file_service.py` (stateless static utils) | role-match |
| `app/domain/entities/user.py` | model (entity) | data-holder | `app/domain/entities/task.py` | exact |
| `app/domain/entities/api_key.py` | model (entity) | data-holder | `app/domain/entities/task.py` | exact |
| `app/domain/entities/rate_limit_bucket.py` | model (entity) | data-holder | `app/domain/entities/task.py` | exact |
| `app/domain/entities/device_fingerprint.py` | model (entity) | data-holder | `app/domain/entities/task.py` | exact |
| `app/domain/repositories/user_repository.py` | repo interface | CRUD | `app/domain/repositories/task_repository.py` | exact |
| `app/domain/repositories/api_key_repository.py` | repo interface | CRUD | `app/domain/repositories/task_repository.py` | exact |
| `app/domain/repositories/rate_limit_repository.py` | repo interface | CRUD | `app/domain/repositories/task_repository.py` | exact |
| `app/domain/repositories/device_fingerprint_repository.py` | repo interface | CRUD | `app/domain/repositories/task_repository.py` | exact |
| `app/infrastructure/database/repositories/sqlalchemy_user_repository.py` | repo impl | CRUD | `app/infrastructure/database/repositories/sqlalchemy_task_repository.py` | exact |
| `app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py` | repo impl | CRUD + indexed prefix lookup | `sqlalchemy_task_repository.py` | exact |
| `app/infrastructure/database/repositories/sqlalchemy_rate_limit_repository.py` | repo impl | CRUD + BEGIN IMMEDIATE | `sqlalchemy_task_repository.py` | exact (extend with txn) |
| `app/infrastructure/database/repositories/sqlalchemy_device_fingerprint_repository.py` | repo impl | CRUD | `sqlalchemy_task_repository.py` | exact |
| `app/infrastructure/database/mappers/user_mapper.py` | mapper | transform | `app/infrastructure/database/mappers/task_mapper.py` | exact |
| `app/infrastructure/database/mappers/api_key_mapper.py` | mapper | transform | `task_mapper.py` | exact |
| `app/infrastructure/database/mappers/rate_limit_bucket_mapper.py` | mapper | transform | `task_mapper.py` | exact |
| `app/infrastructure/database/mappers/device_fingerprint_mapper.py` | mapper | transform | `task_mapper.py` | exact |
| `app/services/auth/__init__.py` | barrel | n/a | `app/services/__init__.py` | exact |
| `app/services/auth/password_service.py` | service | request-response | `app/services/task_management_service.py` | exact |
| `app/services/auth/token_service.py` | service | request-response | `task_management_service.py` | exact |
| `app/services/auth/auth_service.py` | service | orchestration | `task_management_service.py` | exact |
| `app/services/auth/key_service.py` | service | CRUD + verify | `task_management_service.py` | exact |
| `app/services/auth/rate_limit_service.py` | service | CRUD + pure-logic wrap | `task_management_service.py` | exact |
| `app/services/auth/csrf_service.py` | service | request-response | `app/services/file_service.py` | role-match (stateless) |
| `app/core/container.py` (MODIFY) | DI container | n/a | self (extend) | exact |
| `app/core/config.py` (MODIFY) | settings | n/a | self — `class WhisperSettings(BaseSettings)` lines 26-103 | exact |
| `app/core/exceptions.py` (MODIFY) | exceptions | n/a | self — `class TaskNotFoundError(DomainError)` lines 189-206 | exact |
| `app/core/logging.py` (MODIFY) | logging | n/a | self (extend with redaction filter) | partial — no filter analog yet |
| `pyproject.toml` (MODIFY) | manifest | n/a | self — `dependencies = [...]` lines 29-52 | exact |
| `tests/unit/core/test_password_hasher.py` | test | n/a | `tests/unit/services/test_task_management_service.py` | role-match (no DB pure-logic test analog) |
| `tests/unit/core/test_jwt_codec.py` | test | n/a | `tests/unit/services/test_task_management_service.py` | role-match |
| `tests/unit/core/test_api_key.py` | test | n/a | `tests/unit/services/test_task_management_service.py` | role-match |
| `tests/unit/core/test_csrf.py` | test | n/a | `tests/unit/services/test_task_management_service.py` | role-match |
| `tests/unit/core/test_device_fingerprint.py` | test | n/a | `tests/unit/services/test_task_management_service.py` | role-match |
| `tests/unit/core/test_rate_limit.py` | test | n/a | `tests/unit/services/test_task_management_service.py` | role-match |
| `tests/unit/services/auth/test_password_service.py` | test | n/a | `tests/unit/services/test_task_management_service.py` | exact |
| `tests/unit/services/auth/test_token_service.py` | test | n/a | `test_task_management_service.py` | exact |
| `tests/unit/services/auth/test_auth_service.py` | test | n/a | `test_task_management_service.py` | exact |
| `tests/unit/services/auth/test_key_service.py` | test | n/a | `test_task_management_service.py` | exact |
| `tests/unit/services/auth/test_rate_limit_service.py` | test | n/a | `test_task_management_service.py` | exact |
| `tests/unit/services/auth/test_csrf_service.py` | test | n/a | `test_task_management_service.py` | exact |
| `tests/integration/test_argon2_benchmark.py` | test (slow) | n/a | self — uses `@pytest.mark.slow` marker (per `pyproject.toml` line 157) | partial |

---

## Pattern Assignments

### `app/core/password_hasher.py` (utility/core, transform)

**Analog:** `app/core/auth.py` (only existing core security primitive — borrow constant-time compare style)
**Module-level invariant pattern lifted from:** `app/infrastructure/database/models.py` lines 514-521 (assert at module load)

**Module docstring + imports pattern** (model `app/core/auth.py` lines 1-16):
```python
"""Argon2id password hashing and verification.

Single source of truth for hashing user passwords. Wraps argon2-cffi
PasswordHasher with project-locked parameters (m=19456, t=2, p=1).

Per CONTEXT §52-60 (locked):
- Algorithm: Argon2id only.
- Output: PHC-string standard ($argon2id$v=19$m=...$t=...$p=...$<salt>$<hash>).
- Verify: constant-time (library handles internally).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
```

**Module-load invariants** (model `app/infrastructure/database/models.py` lines 510-521 — fail loudly):
```python
# Tiger-style invariants — fail loudly at module load if params drift.
_M_COST = 19456
_T_COST = 2
_PARALLELISM = 1
assert _M_COST == 19456, "Argon2 memory cost drift"
assert _T_COST == 2, "Argon2 time cost drift"
assert _PARALLELISM == 1, "Argon2 parallelism drift"

# PasswordHasher instantiated once at module load (per CONTEXT §150 DRY).
_HASHER = PasswordHasher(
    memory_cost=_M_COST,
    time_cost=_T_COST,
    parallelism=_PARALLELISM,
)
```

**Public API shape** (mirrors `app/services/file_service.py` static-utility style — single-purpose functions):
```python
def hash(plain: str) -> str:
    """Return PHC-string Argon2id hash of plain password."""
    return _HASHER.hash(plain)


def verify(plain: str, hashed: str) -> bool:
    """Constant-time verify; returns False on mismatch (no silent fallback on malformed)."""
    try:
        return _HASHER.verify(hashed, plain)
    except VerifyMismatchError:
        return False
```

---

### `app/core/jwt_codec.py` (utility/core, transform — single jwt.decode site)

**Analog:** none — green-field. Use module-load invariant style from `app/infrastructure/database/models.py` lines 510-521.

**Imports + module-level config**:
```python
"""Single source of truth for JWT encode/decode.

Per CONTEXT §62-71 (locked):
- HS256 only — algorithms=["HS256"] always.
- Token shape: {"sub","iat","exp","ver","method"}.
- Verifier greps `jwt.decode(` across app/ — only this module may match.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.exceptions import (
    JwtAlgorithmError, JwtExpiredError, JwtTamperedError,
)

_ALGORITHM = "HS256"
assert _ALGORITHM == "HS256", "JWT algorithm drift"
```

**Encode/decode pair** (only place `jwt.decode` is allowed):
```python
def encode_session(
    *, user_id: int, token_version: int, secret: str, ttl_days: int = 7,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl_days)).timestamp()),
        "ver": token_version,
        "method": "session",
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_session(token: str, *, secret: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise JwtExpiredError() from e
    except jwt.InvalidAlgorithmError as e:
        raise JwtAlgorithmError(str(e)) from e
    except jwt.InvalidTokenError as e:
        raise JwtTamperedError(str(e)) from e
```

---

### `app/core/api_key.py` (utility/core, transform)

**Analog:** `app/core/auth.py` lines 73-77 (`secrets.compare_digest` constant-time pattern).

**Module-level invariants** (excerpt to copy):
```python
"""whsk_<prefix>_<body> API key generate/verify/parse.

Per CONTEXT §72-82 (locked): 36-char total, 8-char prefix indexed,
SHA-256 hex storage, secrets.compare_digest verify.
"""
import hashlib
import secrets
from app.core.exceptions import InvalidApiKeyFormatError

_KEY_PREFIX = "whsk_"
_PREFIX_LENGTH = 8
_BODY_LENGTH = 22
_TOTAL_LENGTH = len(_KEY_PREFIX) + _PREFIX_LENGTH + 1 + _BODY_LENGTH  # whsk_ + 8 + _ + 22

assert _TOTAL_LENGTH == 36, "API key total length drift"
assert _PREFIX_LENGTH == 8, "API key prefix length drift"
```

**Shared helper (DRY across api_key + device_fingerprint + csrf)**:
```python
def _sha256_hex(s: str) -> str:
    """Return SHA-256 hex digest (64 chars) of UTF-8-encoded input."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
```

**Constant-time verify** (lifted from `app/core/auth.py` line 76):
```python
def verify(plaintext: str, stored_hash: str) -> bool:
    """Constant-time SHA-256 hash compare."""
    return secrets.compare_digest(_sha256_hex(plaintext), stored_hash)
```

**Typed-exception guard** (mirror `app/core/exceptions.py` raise style — early return):
```python
def parse_prefix(plaintext: str) -> str:
    if not plaintext.startswith(_KEY_PREFIX):
        raise InvalidApiKeyFormatError(reason="missing whsk_ prefix")
    if len(plaintext) != _TOTAL_LENGTH:
        raise InvalidApiKeyFormatError(reason=f"length {len(plaintext)} != {_TOTAL_LENGTH}")
    return plaintext[len(_KEY_PREFIX) : len(_KEY_PREFIX) + _PREFIX_LENGTH]
```

---

### `app/core/csrf.py` (utility/core, transform)

**Analog:** `app/core/auth.py` lines 73-77 (constant-time compare).
**Shared helper:** import `_sha256_hex` from `app.core.api_key` is forbidden (different module concern); duplicate the helper or extract to `app/core/_hashing.py`. Per CONTEXT §150 DRY, prefer extracting `_sha256_hex` to `app/core/_hashing.py` and reuse from `api_key.py`, `csrf.py`, `device_fingerprint.py`.

**Pattern**:
```python
"""Double-submit CSRF token generate + verify (per CONTEXT §104-109)."""
import secrets

_TOKEN_BYTES = 32
assert _TOKEN_BYTES == 32, "CSRF token byte-length drift"


def generate() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def verify(cookie_token: str, header_token: str) -> bool:
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)
```

---

### `app/core/device_fingerprint.py` (utility/core, transform — pure)

**Analog:** `app/services/file_service.py` lines 21-47 (`@staticmethod secure_filename` pure-string transform).

**Imports + constants** (mirror file_service style):
```python
"""Compute SHA-256 device fingerprint hashes + IP subnet (pure logic).

Per CONTEXT §111-119 (locked): IPv4 → /24, IPv6 → /64.
"""
import ipaddress
from typing import Literal
from app.core._hashing import _sha256_hex  # shared helper

_IPV4_PREFIX = 24
_IPV6_PREFIX = 64
assert _IPV4_PREFIX == 24, "IPv4 subnet prefix drift"
assert _IPV6_PREFIX == 64, "IPv6 subnet prefix drift"
```

**Early-return pure function** (mirror `app/services/file_service.py` line 64-76 guard-clause style):
```python
def compute(
    *, cookie_value: str, user_agent: str, client_ip: str, device_id: str,
) -> dict[str, str]:
    return {
        "cookie_hash": _sha256_hex(cookie_value),
        "ua_hash": _sha256_hex(user_agent),
        "ip_subnet": _ip_subnet(client_ip),
        "device_id": device_id,
    }


def _ip_subnet(client_ip: str) -> str:
    addr = ipaddress.ip_address(client_ip)
    if isinstance(addr, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{client_ip}/{_IPV4_PREFIX}", strict=False))
    return str(ipaddress.ip_network(f"{client_ip}/{_IPV6_PREFIX}", strict=False))
```

---

### `app/core/rate_limit.py` (utility/core, transform — pure token bucket math)

**Analog:** `app/services/file_service.py` static-method style — pure-logic, no I/O.

**Pure function shape**:
```python
"""Pure-logic token bucket math. No DB, no clock side-effects (now passed in).

Per CONTEXT §93-103 (locked): bucket dict {"tokens": int, "last_refill": datetime}.
"""
from __future__ import annotations
from datetime import datetime
from typing import TypedDict


class BucketState(TypedDict):
    tokens: int
    last_refill: datetime


def consume(
    bucket: BucketState, *, tokens_needed: int, now: datetime,
    rate: float, capacity: int,
) -> tuple[BucketState, bool]:
    elapsed = (now - bucket["last_refill"]).total_seconds()
    if elapsed < 0:
        elapsed = 0  # clock skew guard
    refilled = min(capacity, bucket["tokens"] + int(elapsed * rate))
    if refilled < tokens_needed:
        return ({"tokens": refilled, "last_refill": now}, False)
    return ({"tokens": refilled - tokens_needed, "last_refill": now}, True)
```

---

### `app/domain/entities/user.py` (entity, data-holder)

**Analog:** `app/domain/entities/task.py` lines 1-149 — exact role+flow match.

**Imports + dataclass shape** (lift from `task.py` lines 1-54):
```python
"""Domain entity for User — pure Python, framework-free."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class User:
    """Domain entity representing a user account.

    Mirrors ORM User but with no DB-specific concerns. Contains plan-tier
    and trial-state transition methods (similar to Task.mark_as_*).
    """
    id: int | None  # None until persisted
    email: str
    password_hash: str
    plan_tier: str = "trial"
    stripe_customer_id: str | None = None
    token_version: int = 0
    trial_started_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

**Business method pattern** (mirror `Task.mark_as_completed` lines 56-71 — mutate + bump updated_at):
```python
def bump_token_version(self) -> None:
    """Invalidate all existing JWTs (logout-all-devices)."""
    self.token_version += 1
    self.updated_at = datetime.now(timezone.utc)


def start_trial(self) -> None:
    if self.trial_started_at is not None:
        return  # idempotent — early return guard
    self.trial_started_at = datetime.now(timezone.utc)
    self.updated_at = datetime.now(timezone.utc)
```

**`to_dict()` pattern** — mirror `task.py` lines 123-149 exactly.

---

### `app/domain/entities/api_key.py` (entity, data-holder)

**Analog:** `app/domain/entities/task.py` lines 1-149.

```python
@dataclass
class ApiKey:
    id: int | None
    user_id: int
    name: str
    prefix: str
    hash: str
    scopes: str = "transcribe"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    def is_active(self) -> bool:
        return self.revoked_at is None  # mirror Task.is_processing line 96-103

    def mark_used(self, when: datetime) -> None:
        self.last_used_at = when

    def revoke(self) -> None:
        if self.revoked_at is not None:
            return  # idempotent
        self.revoked_at = datetime.now(timezone.utc)
```

---

### `app/domain/entities/rate_limit_bucket.py` and `app/domain/entities/device_fingerprint.py`

Same shape as above; mirror `Task` dataclass, fields per ORM in `app/infrastructure/database/models.py` lines 409-507. No business methods needed for `RateLimitBucket` (pure persistence row); `DeviceFingerprint` is read-only insert-once.

---

### `app/domain/repositories/user_repository.py` (repo interface, CRUD)

**Analog:** `app/domain/repositories/task_repository.py` lines 1-82 — exact match.

**Lift Protocol shape** (lines 1-19):
```python
"""Repository interface for User entity using Protocol for structural typing."""

from typing import Protocol
from app.domain.entities.user import User


class IUserRepository(Protocol):
    """Repository interface for User entity.

    Same docstring shape as ITaskRepository — implementations swap backends
    without affecting business logic.
    """
    def add(self, user: User) -> int: ...
    def get_by_id(self, identifier: int) -> User | None: ...
    def get_by_email(self, email: str) -> User | None: ...
    def update_token_version(self, identifier: int, new_version: int) -> None: ...
    def update(self, identifier: int, update_data: dict) -> None: ...
```

**Per-method docstring template** (mirror `task_repository.py` lines 20-33):
```python
def get_by_email(self, email: str) -> User | None:
    """
    Get a user by email address.

    Args:
        email: The email of the user to retrieve

    Returns:
        User | None: The User entity if found, None otherwise
    """
    ...
```

---

### `app/domain/repositories/api_key_repository.py` (repo interface)

Same shape; methods needed:
- `add(api_key: ApiKey) -> int`
- `get_by_prefix(prefix: str) -> list[ApiKey]` (uses idx_api_keys_prefix from Phase 10)
- `get_by_user(user_id: int) -> list[ApiKey]`
- `mark_used(identifier: int, when: datetime) -> None`
- `revoke(identifier: int) -> None`

---

### `app/domain/repositories/rate_limit_repository.py` and `device_fingerprint_repository.py`

Same Protocol pattern; specific methods:
- `IRateLimitRepository`: `get_by_key(bucket_key) -> RateLimitBucket | None`, `upsert_atomic(bucket) -> None` (BEGIN IMMEDIATE wrapping read+update)
- `IDeviceFingerprintRepository`: `add(fp) -> int`, `get_recent_for_user(user_id, limit) -> list[DeviceFingerprint]`

---

### `app/infrastructure/database/repositories/sqlalchemy_user_repository.py` (repo impl, CRUD)

**Analog:** `app/infrastructure/database/repositories/sqlalchemy_task_repository.py` lines 1-184 — exact match.

**Class skeleton** (lift lines 1-34):
```python
"""SQLAlchemy implementation of the IUserRepository interface."""

from typing import Any
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.user import User as DomainUser
from app.infrastructure.database.mappers.user_mapper import to_domain, to_orm
from app.infrastructure.database.models import User as ORMUser


class SQLAlchemyUserRepository:
    """SQLAlchemy implementation of the IUserRepository interface."""

    def __init__(self, session: Session):
        self.session = session
```

**add() pattern** — lift `sqlalchemy_task_repository.py` lines 36-70 verbatim, swap Task→User. **CRITICAL** — same `try/except SQLAlchemyError → rollback → raise DatabaseOperationError(operation="add", ...)` pattern. No silent fallback.

**get_by_email() — extends get_by_id pattern** (lines 72-96):
```python
def get_by_email(self, email: str) -> DomainUser | None:
    try:
        orm_user = (
            self.session.query(ORMUser).filter(ORMUser.email == email).first()
        )
        if orm_user:
            logger.debug(f"User found with email: {email}")
            return to_domain(orm_user)
        logger.debug(f"User not found with email: {email}")
        return None
    except SQLAlchemyError as e:
        logger.error(f"Failed to get user by email {email}: {str(e)}")
        return None
```

**Logging — never log password hashes**: replace `f"User added successfully with id: {orm_user.id}"` (no `password_hash` field reference) — verifier greps for `password` substring in log calls.

---

### `app/infrastructure/database/repositories/sqlalchemy_api_key_repository.py` (repo impl, CRUD + indexed prefix lookup)

**Analog:** `sqlalchemy_task_repository.py`. Add prefix-indexed lookup:
```python
def get_by_prefix(self, prefix: str) -> list[DomainApiKey]:
    """Indexed lookup using idx_api_keys_prefix (created in Phase 10)."""
    try:
        orm_keys = (
            self.session.query(ORMApiKey)
            .filter(ORMApiKey.prefix == prefix)
            .filter(ORMApiKey.revoked_at.is_(None))
            .all()
        )
        return [to_domain(k) for k in orm_keys]
    except SQLAlchemyError as e:
        logger.error(f"Failed to get keys by prefix={prefix}: {str(e)}")
        return []
```

**Logging — only log `prefix`, never the full key** (per CONTEXT §86-90).

---

### `app/infrastructure/database/repositories/sqlalchemy_rate_limit_repository.py` (repo impl, BEGIN IMMEDIATE)

**Analog:** `sqlalchemy_task_repository.py` for skeleton, but adds explicit transaction wrapping for SQLite worker-safety (per CONTEXT §98 locked).

**Atomic upsert pattern** — extends update() lines 116-154:
```python
def upsert_atomic(self, bucket_key: str, new_state: dict) -> None:
    """Read-modify-write under BEGIN IMMEDIATE for SQLite worker-safety."""
    try:
        # SQLite-specific: BEGIN IMMEDIATE escalates to RESERVED lock
        self.session.execute(text("BEGIN IMMEDIATE"))
        orm_bucket = (
            self.session.query(ORMBucket)
            .filter(ORMBucket.bucket_key == bucket_key)
            .first()
        )
        if orm_bucket is None:
            orm_bucket = ORMBucket(bucket_key=bucket_key, **new_state)
            self.session.add(orm_bucket)
        else:
            orm_bucket.tokens = new_state["tokens"]
            orm_bucket.last_refill = new_state["last_refill"]
        self.session.commit()
    except SQLAlchemyError as e:
        self.session.rollback()
        logger.error(f"Failed to upsert bucket {bucket_key}: {str(e)}")
        raise DatabaseOperationError(operation="upsert_rate_limit", reason=str(e), original_error=e)
```

---

### `app/infrastructure/database/repositories/sqlalchemy_device_fingerprint_repository.py`

Append-only insert pattern — copy `add()` from `sqlalchemy_task_repository.py` lines 36-70, drop update/delete methods.

---

### `app/infrastructure/database/mappers/user_mapper.py` (mapper, transform)

**Analog:** `app/infrastructure/database/mappers/task_mapper.py` lines 1-69 — exact match.

**Pattern** (lift lines 7-36 verbatim, swap Task→User):
```python
"""Mapper functions for converting between domain and ORM User models."""

from app.domain.entities.user import User as DomainUser
from app.infrastructure.database.models import User as ORMUser


def to_domain(orm_user: ORMUser) -> DomainUser:
    return DomainUser(
        id=orm_user.id,
        email=orm_user.email,
        password_hash=orm_user.password_hash,
        plan_tier=orm_user.plan_tier,
        stripe_customer_id=orm_user.stripe_customer_id,
        token_version=orm_user.token_version,
        trial_started_at=orm_user.trial_started_at,
        created_at=orm_user.created_at,
        updated_at=orm_user.updated_at,
    )


def to_orm(domain_user: DomainUser) -> ORMUser:
    return ORMUser(
        email=domain_user.email,
        password_hash=domain_user.password_hash,
        plan_tier=domain_user.plan_tier,
        stripe_customer_id=domain_user.stripe_customer_id,
        token_version=domain_user.token_version,
        trial_started_at=domain_user.trial_started_at,
        created_at=domain_user.created_at,
        updated_at=domain_user.updated_at,
    )
```

**Update barrel** `app/infrastructure/database/mappers/__init__.py` — add new exports following the existing line-3-5 pattern.

---

### `app/services/auth/__init__.py` (barrel)

**Analog:** `app/services/__init__.py` lines 1-36 (exact pattern).

```python
"""Auth services layer — orchestration on top of pure-logic core modules."""

from app.services.auth.auth_service import AuthService
from app.services.auth.csrf_service import CsrfService
from app.services.auth.key_service import KeyService
from app.services.auth.password_service import PasswordService
from app.services.auth.rate_limit_service import RateLimitService
from app.services.auth.token_service import TokenService

__all__ = [
    "AuthService",
    "CsrfService",
    "KeyService",
    "PasswordService",
    "RateLimitService",
    "TokenService",
]
```

---

### `app/services/auth/password_service.py` (service)

**Analog:** `app/services/task_management_service.py` lines 1-104 — exact match.

**Class skeleton** (lift lines 1-24):
```python
"""Service for password hashing and verification."""

from app.core import password_hasher
from app.core.exceptions import InvalidCredentialsError
from app.core.logging import logger


class PasswordService:
    """Stateless wrapper around app.core.password_hasher.

    Single responsibility: hash and verify passwords. NO storage,
    NO user lookup (that's AuthService).
    """

    def hash_password(self, plain: str) -> str:
        logger.debug("Hashing password (length redacted)")
        return password_hasher.hash(plain)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return password_hasher.verify(plain, hashed)
```

**No constructor** — stateless, becomes `providers.Singleton`.

---

### `app/services/auth/token_service.py` (service)

**Analog:** `app/services/task_management_service.py` lines 17-24 (`__init__`-with-deps shape).

**Constructor pattern** — mirror `TaskManagementService.__init__`:
```python
class TokenService:
    """Wraps app.core.jwt_codec; issues sliding-expiry session tokens."""

    def __init__(self, secret: str, ttl_days: int = 7) -> None:
        self.secret = secret
        self.ttl_days = ttl_days

    def issue(self, user_id: int, token_version: int) -> str:
        return jwt_codec.encode_session(
            user_id=user_id, token_version=token_version,
            secret=self.secret, ttl_days=self.ttl_days,
        )

    def verify_and_refresh(self, token: str, current_token_version: int) -> tuple[dict, str]:
        payload = jwt_codec.decode_session(token, secret=self.secret)
        if payload["ver"] != current_token_version:
            raise JwtTamperedError("token version mismatch")
        new_token = self.issue(payload["sub"], current_token_version)
        return payload, new_token
```

---

### `app/services/auth/auth_service.py` (service, orchestration)

**Analog:** `app/services/task_management_service.py` lines 17-104 — multi-dep service composition.

**Constructor + dependency injection** (mirror lines 17-24):
```python
class AuthService:
    """Orchestrates user registration + login.

    Dependencies (per CONTEXT §131): IUserRepository + PasswordService + TokenService.
    """

    def __init__(
        self,
        user_repository: IUserRepository,
        password_service: PasswordService,
        token_service: TokenService,
    ) -> None:
        self.user_repository = user_repository
        self.password_service = password_service
        self.token_service = token_service
```

**Method pattern** (mirror `create_task` lines 26-39 — debug-log → repo call → info-log → return):
```python
def register(self, email: str, plain_password: str) -> User:
    logger.debug("Registering user (email redacted)")
    if self.user_repository.get_by_email(email) is not None:
        raise UserAlreadyExistsError(email=email)
    hashed = self.password_service.hash_password(plain_password)
    user = User(id=None, email=email, password_hash=hashed)
    new_id = self.user_repository.add(user)
    user.id = new_id
    logger.info("User registered with id: %s", new_id)  # NEVER log email/password
    return user


def login(self, email: str, plain_password: str) -> tuple[User, str]:
    user = self.user_repository.get_by_email(email)
    if user is None:
        raise InvalidCredentialsError()  # generic — don't reveal which leg failed
    if not self.password_service.verify_password(plain_password, user.password_hash):
        raise InvalidCredentialsError()
    token = self.token_service.issue(user.id, user.token_version)
    logger.info("User logged in: id=%s", user.id)  # never email
    return user, token
```

---

### `app/services/auth/key_service.py` (service)

Same pattern. Composes `IApiKeyRepository` + `app.core.api_key`. Method `create_key(user_id, name)` returns plaintext **once** (per CONTEXT §211); after that only hash + prefix on disk.

---

### `app/services/auth/rate_limit_service.py` (service, pure-logic wrap)

Composes `IRateLimitRepository` + `app.core.rate_limit`. Method `check_and_consume(bucket_key, tokens_needed, rate, capacity)` reads bucket, calls `rate_limit.consume()`, persists via `repo.upsert_atomic`.

---

### `app/services/auth/csrf_service.py` (service)

Stateless singleton (mirror `FileService` static-method pattern). Wraps `app.core.csrf` — issue + verify only.

---

## Modify Existing

### `app/core/container.py` (extend)

**Self-analog:** lines 47-87 (existing providers).

**Pattern to follow** — append after line 87:
```python
    # Auth Repositories - Factory pattern with session dependency
    user_repository = providers.Factory(
        SQLAlchemyUserRepository,
        session=db_session_factory,
    )
    api_key_repository = providers.Factory(
        SQLAlchemyApiKeyRepository,
        session=db_session_factory,
    )
    rate_limit_repository = providers.Factory(
        SQLAlchemyRateLimitRepository,
        session=db_session_factory,
    )
    device_fingerprint_repository = providers.Factory(
        SQLAlchemyDeviceFingerprintRepository,
        session=db_session_factory,
    )

    # Auth Services - Singletons for stateless, Factories for stateful
    password_service = providers.Singleton(PasswordService)
    csrf_service = providers.Singleton(CsrfService)
    token_service = providers.Singleton(
        TokenService,
        secret=config.provided.auth.JWT_SECRET,
    )
    auth_service = providers.Factory(
        AuthService,
        user_repository=user_repository,
        password_service=password_service,
        token_service=token_service,
    )
    key_service = providers.Factory(
        KeyService,
        repository=api_key_repository,
    )
    rate_limit_service = providers.Factory(
        RateLimitService,
        repository=rate_limit_repository,
    )
```

**Note:** `config.provided.auth.JWT_SECRET` — mirrors line 78 `config.provided.whisper.HF_TOKEN`.

---

### `app/core/config.py` (extend)

**Self-analog:** `class WhisperSettings(BaseSettings)` lines 26-103.

**Pattern** — add new nested class before `class Settings` (line 136), then register on `Settings` like line 158:
```python
class AuthSettings(BaseSettings):
    """Authentication configuration settings."""

    JWT_SECRET: SecretStr = Field(
        ...,  # required — fail loudly if missing
        description="HS256 secret for session tokens",
    )
    JWT_TTL_DAYS: int = Field(default=7, description="JWT validity period (days)")
    ARGON2_M_COST: int = Field(default=19456, description="Argon2 memory cost (KiB)")
    ARGON2_T_COST: int = Field(default=2, description="Argon2 time cost (iterations)")
    ARGON2_PARALLELISM: int = Field(default=1, description="Argon2 parallelism")
    CSRF_SECRET: SecretStr = Field(..., description="CSRF token signing secret")
```

Then add to `class Settings` after line 160 (mirror nested registration):
```python
    auth: AuthSettings = Field(default_factory=AuthSettings)
```

`SecretStr` import — add to line 7 alongside `Field`.

---

### `app/core/exceptions.py` (extend)

**Self-analog:** `class TaskNotFoundError(DomainError)` lines 189-206.

**Add at end of file** (after line 603, mirror that exact constructor shape):
```python
# Auth-related exceptions

class InvalidCredentialsError(DomainError):
    """Generic 'email or password wrong' — must NOT reveal which leg failed."""
    def __init__(self, correlation_id: Optional[str] = None) -> None:
        super().__init__(
            message="Invalid credentials",
            code="INVALID_CREDENTIALS",
            user_message="Invalid email or password.",
            correlation_id=correlation_id,
        )


class UserAlreadyExistsError(ValidationError):
    def __init__(self, email: str) -> None:
        super().__init__(
            message=f"User with email already exists",  # do NOT include email in `message`
            code="USER_ALREADY_EXISTS",
            user_message="An account with this email already exists.",
            field="email",
        )


class InvalidApiKeyFormatError(ValidationError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Invalid API key format: {reason}",
            code="INVALID_API_KEY_FORMAT",
            user_message="The provided API key is malformed.",
            reason=reason,
        )


class InvalidApiKeyHashError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            message="API key hash mismatch",
            code="INVALID_API_KEY",
            user_message="The provided API key is invalid.",
        )


class JwtAlgorithmError(DomainError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            message=f"JWT algorithm rejected: {detail}",
            code="JWT_ALGORITHM_ERROR",
            user_message="Authentication token is invalid.",
            detail=detail,
        )


class JwtExpiredError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            message="JWT expired",
            code="JWT_EXPIRED",
            user_message="Your session has expired. Please log in again.",
        )


class JwtTamperedError(DomainError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            message=f"JWT signature/claims invalid: {detail}",
            code="JWT_TAMPERED",
            user_message="Authentication token is invalid.",
        )


class WeakPasswordError(ValidationError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Password rejected: {reason}",
            code="WEAK_PASSWORD",
            user_message=f"Password is too weak: {reason}",
            reason=reason,
        )


class RateLimitExceededError(DomainError):
    def __init__(self, bucket_key: str, retry_after_seconds: int) -> None:
        super().__init__(
            message=f"Rate limit exceeded for bucket={bucket_key}",
            code="RATE_LIMIT_EXCEEDED",
            user_message="Too many requests. Please try again later.",
            retry_after_seconds=retry_after_seconds,
        )
```

---

### `app/core/logging.py` (extend with redaction filter)

**Self-analog:** lines 1-43 (existing setup).

**Add new module** `app/core/_log_redaction.py` (preferred — SRP) with class `RedactingFilter(logging.Filter)`:
```python
"""Logging filter that redacts sensitive substrings from structured fields.

Per CONTEXT §83-90 (locked): redact `password`, `secret`, `api_key`, `token` keys.
"""
import logging
import re

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|secret|api_key|token)", re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Redact sensitive structured fields
        for attr in list(record.__dict__):
            if _SENSITIVE_KEY_PATTERN.search(attr):
                setattr(record, attr, _REDACTED)
        # Redact in formatted message args (best-effort — keep keys, scrub values)
        if isinstance(record.args, dict):
            record.args = {
                k: (_REDACTED if _SENSITIVE_KEY_PATTERN.search(k) else v)
                for k, v in record.args.items()
            }
        return True
```

Then in `app/core/logging.py` after line 38, attach the filter:
```python
from app.core._log_redaction import RedactingFilter
logger.addFilter(RedactingFilter())
```

---

### `pyproject.toml` (modify dependencies)

**Self-analog:** lines 29-52 (existing `dependencies = [...]`).

Append (preserve sorting alphabetical-ish where possible, but project uses functional grouping):
```toml
    "argon2-cffi>=23.1.0",  # Argon2id password hashing (CONTEXT §52-60)
    "pyjwt>=2.8.0",         # JWT HS256 encode/decode (CONTEXT §62-71)
```

---

## Tests — Pattern Assignments

### `tests/unit/core/test_password_hasher.py` (and other core tests)

**Analog:** No exact analog (no pure-logic core test exists). Use `tests/unit/services/test_task_management_service.py` lines 1-142 for class-based test scaffolding.

**Skeleton**:
```python
"""Unit tests for app.core.password_hasher."""
import pytest
from app.core import password_hasher


@pytest.mark.unit
class TestPasswordHasher:
    def test_hash_returns_phc_string(self) -> None:
        result = password_hasher.hash("test-password-123")
        assert result.startswith("$argon2id$")

    def test_verify_correct_password_returns_true(self) -> None:
        hashed = password_hasher.hash("correct-horse-battery-staple")
        assert password_hasher.verify("correct-horse-battery-staple", hashed) is True

    def test_verify_wrong_password_returns_false(self) -> None:
        hashed = password_hasher.hash("correct")
        assert password_hasher.verify("wrong", hashed) is False

    def test_verify_malformed_hash_returns_false(self) -> None:
        # No silent crash — typed False return on garbage input
        assert password_hasher.verify("any", "not-a-phc-string") is False

    def test_two_hashes_of_same_input_differ(self) -> None:
        # Salt randomization
        h1 = password_hasher.hash("same-input")
        h2 = password_hasher.hash("same-input")
        assert h1 != h2
```

---

### `tests/unit/services/auth/test_password_service.py` (and other service tests)

**Analog:** `tests/unit/services/test_task_management_service.py` lines 1-142 — exact match.

**Lift fixture+test pattern verbatim**, swap entity/service:
```python
"""Unit tests for PasswordService."""
from unittest.mock import MagicMock
import pytest
from app.services.auth.password_service import PasswordService


@pytest.mark.unit
class TestPasswordService:
    @pytest.fixture
    def service(self) -> PasswordService:
        return PasswordService()

    def test_hash_then_verify_succeeds(self, service: PasswordService) -> None:
        hashed = service.hash_password("hunter2")
        assert service.verify_password("hunter2", hashed) is True

    def test_verify_wrong_password_returns_false(self, service: PasswordService) -> None:
        hashed = service.hash_password("hunter2")
        assert service.verify_password("wrong", hashed) is False
```

For `test_auth_service.py` — mock all three deps (mirror line 14-22 mock_repository fixture):
```python
@pytest.fixture
def mock_user_repo(self) -> MagicMock:
    return MagicMock()

@pytest.fixture
def mock_password_service(self) -> MagicMock:
    return MagicMock()

@pytest.fixture
def mock_token_service(self) -> MagicMock:
    return MagicMock()

@pytest.fixture
def service(self, mock_user_repo, mock_password_service, mock_token_service) -> AuthService:
    return AuthService(mock_user_repo, mock_password_service, mock_token_service)
```

---

### `tests/integration/test_argon2_benchmark.py` (slow)

**Analog:** `pyproject.toml` line 157 declares `slow` marker. No existing slow benchmark — green-field.

**Pattern**:
```python
"""CI benchmark: 100 Argon2id hashes p99 < 300ms (per CONTEXT §38, §210)."""
import time
import pytest
from app.core import password_hasher


@pytest.mark.slow
@pytest.mark.integration
class TestArgon2Benchmark:
    def test_p99_under_300ms(self) -> None:
        durations: list[float] = []
        for i in range(100):
            t0 = time.perf_counter()
            password_hasher.hash(f"benchmark-pwd-{i}")
            durations.append((time.perf_counter() - t0) * 1000)
        durations.sort()
        p99 = durations[98]  # index 98 of 100 sorted = p99
        assert p99 < 300, f"Argon2 p99={p99:.1f}ms exceeded 300ms budget"
```

Run via `pytest -m slow tests/integration/test_argon2_benchmark.py` (gated out of default per CONTEXT §210).

---

## Shared Patterns

### Shared SHA-256 Helper (DRY — extract to `app/core/_hashing.py`)

**Per CONTEXT §150 (locked):** `_sha256_hex(s: str) -> str` MUST be a single shared helper. Don't duplicate across `api_key.py`, `csrf.py`, `device_fingerprint.py`.

**Source:** new file `app/core/_hashing.py`:
```python
"""Shared cryptographic primitives — DRY reuse across api_key/csrf/device_fingerprint."""
import hashlib

def _sha256_hex(s: str) -> str:
    """Return SHA-256 hex digest (64 chars) of UTF-8-encoded input."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
```
**Apply to:** `app/core/api_key.py`, `app/core/csrf.py`, `app/core/device_fingerprint.py`.

---

### Constant-Time Compare

**Source:** `app/core/auth.py` line 76 (`secrets.compare_digest`)
**Apply to:** `app/core/api_key.py:verify`, `app/core/csrf.py:verify`, any place comparing secrets/hashes.
```python
return secrets.compare_digest(provided, expected)
```

---

### Tiger-Style Module-Load Invariants

**Source:** `app/infrastructure/database/models.py` lines 510-521.
**Apply to:** every new core module (`password_hasher`, `jwt_codec`, `api_key`, `csrf`, `device_fingerprint`, `rate_limit`).
```python
# Tiger-style invariants — fail loudly at module load if params drift.
assert _CONST == EXPECTED, "<const> drift"
```

---

### Repository Error-Handling Wrapper

**Source:** `app/infrastructure/database/repositories/sqlalchemy_task_repository.py` lines 49-70 (try/except SQLAlchemyError → rollback → raise DatabaseOperationError)
**Apply to:** ALL new SQLAlchemy repository write methods (add/update/delete/upsert).
```python
try:
    # ... db ops ...
    self.session.commit()
except SQLAlchemyError as e:
    self.session.rollback()
    logger.error(f"Failed to <op>: {str(e)}")
    raise DatabaseOperationError(operation="<op>", reason=str(e), original_error=e)
```

---

### Service Logging — Sensitive Field Suppression

**Source:** CONTEXT §83-90 (locked).
**Apply to:** ALL new auth services. Pattern:
- Log `id=42` not `email=foo@bar.com`
- Log `prefix=abc12345` not full key plaintext
- Log `sub=42 exp=...` not raw JWT token
- NEVER log `password`, `JWT_SECRET`, full `api_key`
- The `RedactingFilter` (added in `app/core/logging.py`) is a defense-in-depth net — don't rely on it for primary protection.

---

### Typed Domain Exceptions (no silent fallback)

**Source:** `app/core/exceptions.py` lines 66-83 (`DomainError` base) + lines 189-206 (TaskNotFoundError example).
**Apply to:** every error path in core modules + services.

Pattern:
```python
if not valid:
    raise <SpecificError>(<context_kwargs>)
return value
```
NOT:
```python
if not valid:
    return None  # silent fallback — FORBIDDEN per CONTEXT §152
```

---

### DI Provider Registration

**Source:** `app/core/container.py` lines 49-87 (existing providers).
**Apply to:** all new auth providers.
- **Stateless** → `providers.Singleton`
- **Stateful (DB session bound)** → `providers.Factory`
- **Config-bound secrets** → `config.provided.auth.JWT_SECRET` (mirror line 78 HF_TOKEN)

---

### Test Class + Fixture Skeleton

**Source:** `tests/unit/services/test_task_management_service.py` lines 1-50.
**Apply to:** all new service tests.
- `@pytest.mark.unit` decorator on class
- `@pytest.fixture` per dep (MagicMock)
- `service` fixture composing all mocks
- `sample_*` fixture per entity

---

## Barrel-File Updates

| Barrel | Lines reference | Action |
|---|---|---|
| `app/domain/entities/__init__.py` | mirror existing | add `User`, `ApiKey`, `RateLimitBucket`, `DeviceFingerprint` |
| `app/domain/repositories/__init__.py` | lines 1-5 | add 4 new `I*Repository` exports |
| `app/infrastructure/database/mappers/__init__.py` | lines 1-5 | add 4 new mapper module exports |
| `app/services/__init__.py` | lines 20-36 (extend `__all__`) | add `AuthService`, `KeyService`, etc. (or just re-export from `app.services.auth`) |
| `app/core/__init__.py` | lines 5-7 | optionally re-export `password_hasher`, `jwt_codec`, `api_key` (slim public surface per CONTEXT §163) |

---

## No Analog Found

| File | Role | Reason | Mitigation |
|---|---|---|---|
| `app/core/jwt_codec.py` | utility/transform | No JWT codec exists yet | Use module-load invariant pattern from `models.py` |
| `app/core/password_hasher.py` | utility/transform | No Argon2 wrapper exists | Use stateless `FileService`-style static module |
| `app/core/_log_redaction.py` (helper) | logging filter | No filter analog in `app/core/logging.py` | Standard Python `logging.Filter` subclass |
| `tests/integration/test_argon2_benchmark.py` | slow benchmark | No existing benchmark test | Use `pyproject.toml` line 157 `slow` marker |

---

## Metadata

**Analog search scope:** `app/core/`, `app/domain/`, `app/infrastructure/database/`, `app/services/`, `tests/unit/`
**Files scanned:** 21
**Pattern extraction date:** 2026-04-29
**Verification gates planner must propagate:**
- `grep -rn "jwt.decode(" app/` → exactly 1 hit (`app/core/jwt_codec.py`)
- `grep -cE "^if .*if " app/core/*.py` → 0 (max 2 nesting)
- log-output greps for `password|JWT_SECRET|<full whsk_ key>` → 0 hits across services
- module-load asserts present in every new `app/core/*.py` (tiger-style)
- `_sha256_hex` defined exactly once (DRY)
