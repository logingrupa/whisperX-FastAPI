"""Argon2id password hashing and verification.

Single source of truth for hashing user passwords. Wraps argon2-cffi
PasswordHasher with project-locked parameters (m=19456, t=2, p=1).

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §52-60 (locked):
- Algorithm: Argon2id only.
- Output: PHC-string standard ($argon2id$v=19$m=...$t=...$p=...$<salt>$<hash>).
- Verify: constant-time (library handles internally).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

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


def hash(plain: str) -> str:
    """Return PHC-string Argon2id hash of plain password."""
    return _HASHER.hash(plain)


def verify(plain: str, hashed: str) -> bool:
    """Constant-time verify. Returns False on mismatch or malformed hash."""
    try:
        return _HASHER.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False
