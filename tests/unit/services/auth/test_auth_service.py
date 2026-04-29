"""Unit tests for AuthService (mocks IUserRepository, PasswordService, TokenService)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from app.domain.entities.user import User
from app.services.auth.auth_service import AuthService


@pytest.mark.unit
class TestAuthService:
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
    def service(
        self,
        mock_user_repo: MagicMock,
        mock_password_service: MagicMock,
        mock_token_service: MagicMock,
    ) -> AuthService:
        return AuthService(mock_user_repo, mock_password_service, mock_token_service)

    def test_register_creates_new_user(
        self,
        service: AuthService,
        mock_user_repo: MagicMock,
        mock_password_service: MagicMock,
    ) -> None:
        mock_user_repo.get_by_email.return_value = None
        mock_password_service.hash_password.return_value = "$argon2id$..."
        mock_user_repo.add.return_value = 7
        result = service.register("a@b.com", "pw")
        assert result.id == 7
        assert result.password_hash == "$argon2id$..."
        mock_user_repo.add.assert_called_once()

    def test_register_duplicate_email_raises(
        self,
        service: AuthService,
        mock_user_repo: MagicMock,
        mock_password_service: MagicMock,
    ) -> None:
        mock_user_repo.get_by_email.return_value = User(
            id=1, email="a@b.com", password_hash="h",
        )
        with pytest.raises(UserAlreadyExistsError):
            service.register("a@b.com", "pw")
        # No password hashing on duplicate path.
        mock_password_service.hash_password.assert_not_called()

    def test_login_missing_user_raises_invalid_credentials(
        self,
        service: AuthService,
        mock_user_repo: MagicMock,
        mock_password_service: MagicMock,
    ) -> None:
        mock_user_repo.get_by_email.return_value = None
        with pytest.raises(InvalidCredentialsError):
            service.login("a@b.com", "pw")
        # No verify call on missing user (timing trade-off documented in service).
        mock_password_service.verify_password.assert_not_called()

    def test_login_wrong_password_raises_invalid_credentials(
        self,
        service: AuthService,
        mock_user_repo: MagicMock,
        mock_password_service: MagicMock,
    ) -> None:
        mock_user_repo.get_by_email.return_value = User(
            id=1, email="a@b.com", password_hash="h",
        )
        mock_password_service.verify_password.return_value = False
        with pytest.raises(InvalidCredentialsError):
            service.login("a@b.com", "pw")

    def test_login_success_returns_user_and_token(
        self,
        service: AuthService,
        mock_user_repo: MagicMock,
        mock_password_service: MagicMock,
        mock_token_service: MagicMock,
    ) -> None:
        mock_user_repo.get_by_email.return_value = User(
            id=1, email="a@b.com", password_hash="h", token_version=3,
        )
        mock_password_service.verify_password.return_value = True
        mock_token_service.issue.return_value = "jwt.token.here"
        user, token = service.login("a@b.com", "pw")
        assert user.id == 1
        assert token == "jwt.token.here"
        mock_token_service.issue.assert_called_once_with(1, 3)
