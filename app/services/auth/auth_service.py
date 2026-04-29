"""AuthService — orchestrates registration, login, and logout-all-devices.

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §131 (locked):
dependencies = IUserRepository + PasswordService + TokenService.
"""

from __future__ import annotations

from app.core.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from app.core.logging import logger
from app.domain.entities.user import User
from app.domain.repositories.user_repository import IUserRepository
from app.services.auth.password_service import PasswordService
from app.services.auth.token_service import TokenService


class AuthService:
    """Orchestrates user registration + login + logout-all-devices.

    Logging discipline (AUTH-09):
      - log ``id=N`` only — never email, never password, never raw token.
      - login() uses generic InvalidCredentialsError on either leg failing
        to avoid email-enumeration via differential responses.

    Trade-off: login() returns early on missing user without calling
    verify_password, which creates a small timing-oracle (registered-vs-
    unregistered email is ~Argon2-time slower). Accepted because (a)
    ANTI-02 throttles login at 10/hr/IP making bulk enumeration impractical,
    and (b) the alternative (calling verify against a dummy hash to equalize
    timing) wastes Argon2 CPU on every miss.
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

    def register(self, email: str, plain_password: str) -> User:
        """Register a new user.

        Raises UserAlreadyExistsError if email already taken.
        """
        logger.debug("AuthService.register called")
        existing = self.user_repository.get_by_email(email)
        if existing is not None:
            raise UserAlreadyExistsError()
        hashed = self.password_service.hash_password(plain_password)
        user = User(id=None, email=email, password_hash=hashed)
        new_id = self.user_repository.add(user)
        user.id = new_id
        logger.info("User registered id=%s", new_id)
        return user

    def login(self, email: str, plain_password: str) -> tuple[User, str]:
        """Verify credentials + issue session token. Generic error on failure."""
        user = self.user_repository.get_by_email(email)
        if user is None:
            raise InvalidCredentialsError()
        if not self.password_service.verify_password(
            plain_password, user.password_hash
        ):
            raise InvalidCredentialsError()
        token = self.token_service.issue(int(user.id), user.token_version)
        logger.info("User logged in id=%s", user.id)
        return user, token

    def logout_all_devices(self, user_id: int) -> None:
        """Bump users.token_version — every existing JWT for this user invalidates."""
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError()
        self.user_repository.update_token_version(user_id, user.token_version + 1)
        logger.info("Logout-all-devices id=%s", user_id)
