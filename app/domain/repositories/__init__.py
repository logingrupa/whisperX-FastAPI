"""Repository interfaces - Abstract interfaces for data access."""

from app.domain.repositories.api_key_repository import IApiKeyRepository
from app.domain.repositories.device_fingerprint_repository import (
    IDeviceFingerprintRepository,
)
from app.domain.repositories.rate_limit_repository import IRateLimitRepository
from app.domain.repositories.task_repository import ITaskRepository
from app.domain.repositories.user_repository import IUserRepository

__all__ = [
    "IApiKeyRepository",
    "IDeviceFingerprintRepository",
    "IRateLimitRepository",
    "ITaskRepository",
    "IUserRepository",
]
