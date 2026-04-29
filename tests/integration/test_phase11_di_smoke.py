"""DI Container smoke test: every Phase 11 auth provider resolves cleanly.

Covers Phase 11 success criterion #4 (PROJECT/ROADMAP):
'DI Container.password_service / token_service / auth_service / key_service /
 rate_limit_service / csrf_service resolve to fresh instances'.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.container import Container
from app.services.auth.auth_service import AuthService
from app.services.auth.csrf_service import CsrfService
from app.services.auth.key_service import KeyService
from app.services.auth.password_service import PasswordService
from app.services.auth.rate_limit_service import RateLimitService
from app.services.auth.token_service import TokenService


@pytest.mark.integration
class TestDiContainerResolution:
    """Smoke: Container() resolves all 6 Phase 11 auth services to correct types."""

    @pytest.fixture
    def container(self) -> Container:
        c = Container()
        # Override db_session_factory so Factory-bound services can resolve
        # without touching a real DB (repos are constructed with a MagicMock
        # session and never queried by the resolution-only smoke tests).
        c.db_session_factory.override(MagicMock())
        return c

    def test_password_service_resolves(self, container: Container) -> None:
        instance = container.password_service()
        assert isinstance(instance, PasswordService)

    def test_csrf_service_resolves(self, container: Container) -> None:
        instance = container.csrf_service()
        assert isinstance(instance, CsrfService)

    def test_token_service_resolves(self, container: Container) -> None:
        instance = container.token_service()
        assert isinstance(instance, TokenService)
        # TokenService is constructed with a string secret (SecretStr unwrapped at DI).
        assert isinstance(instance.secret, str)

    def test_auth_service_resolves(self, container: Container) -> None:
        instance = container.auth_service()
        assert isinstance(instance, AuthService)

    def test_key_service_resolves(self, container: Container) -> None:
        instance = container.key_service()
        assert isinstance(instance, KeyService)

    def test_rate_limit_service_resolves(self, container: Container) -> None:
        instance = container.rate_limit_service()
        assert isinstance(instance, RateLimitService)

    def test_di_container_resolves_all_six_auth_services(
        self, container: Container,
    ) -> None:
        # Sanity: instantiate every locked auth service in one breath.
        services = [
            container.password_service(),
            container.csrf_service(),
            container.token_service(),
            container.auth_service(),
            container.key_service(),
            container.rate_limit_service(),
        ]
        # No None, no exception, exactly 6 resolved.
        assert len(services) == 6
        assert all(s is not None for s in services)
        type_names = [type(s).__name__ for s in services]
        assert type_names == [
            "PasswordService",
            "CsrfService",
            "TokenService",
            "AuthService",
            "KeyService",
            "RateLimitService",
        ]
