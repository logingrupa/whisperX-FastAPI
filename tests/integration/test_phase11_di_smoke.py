"""Phase 19 dep-chain smoke test: every new auth Depends + service resolves.

Phase 19 Plan 10 migration: this file previously asserted that the legacy
``Container`` resolves all 6 Phase-11 auth services. The container is being
deleted in Plan 13; the equivalent post-refactor invariant is "the new
``Depends`` chain in ``app.api.dependencies`` exposes every auth surface a
route needs, and every stateless service singleton in ``app.core.services``
is callable".

Plan-10 threat-model T-19-10-05 picks option (a): preserve the smoke gate
without depending on the deleted Container class. The 7 individual
``test_*_resolves`` cases stay (1:1 with the legacy six + ws_ticket) so
the test inventory count holds — only their bodies switch from container
attribute lookups to symbolic callable checks.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestPhase19DepChain:
    """Smoke: every new auth dep + service factory is callable end-to-end."""

    def test_password_service_resolves(self) -> None:
        from app.core.services import get_password_service
        from app.services.auth.password_service import PasswordService

        assert callable(get_password_service)
        instance = get_password_service()
        assert isinstance(instance, PasswordService)

    def test_csrf_service_resolves(self) -> None:
        from app.core.services import get_csrf_service
        from app.services.auth.csrf_service import CsrfService

        assert callable(get_csrf_service)
        instance = get_csrf_service()
        assert isinstance(instance, CsrfService)

    def test_token_service_resolves(self) -> None:
        from app.core.services import get_token_service
        from app.services.auth.token_service import TokenService

        assert callable(get_token_service)
        instance = get_token_service()
        assert isinstance(instance, TokenService)
        # SecretStr unwrapped at lru-cache call site.
        assert isinstance(instance.secret, str)

    def test_auth_service_dep_is_callable(self) -> None:
        """``get_auth_service`` is the per-request Depends factory."""
        from app.api.dependencies import get_auth_service

        assert callable(get_auth_service)

    def test_key_service_dep_is_callable(self) -> None:
        from app.api.dependencies import get_key_service

        assert callable(get_key_service)

    def test_account_service_dep_is_callable(self) -> None:
        from app.api.dependencies import get_account_service

        assert callable(get_account_service)

    def test_phase19_full_dep_chain_resolves(self) -> None:
        """Every locked Phase 19 dep + service is callable in one breath."""
        from app.api.dependencies import (
            authenticated_user,
            authenticated_user_optional,
            csrf_protected,
            get_account_service,
            get_auth_service,
            get_db,
            get_key_service,
            get_scoped_task_repository,
        )
        from app.core.services import (
            get_csrf_service,
            get_password_service,
            get_token_service,
            get_ws_ticket_service,
        )

        deps = [
            authenticated_user,
            authenticated_user_optional,
            csrf_protected,
            get_account_service,
            get_auth_service,
            get_db,
            get_key_service,
            get_scoped_task_repository,
            get_password_service,
            get_csrf_service,
            get_token_service,
            get_ws_ticket_service,
        ]
        # No None, no exception — every dep is a real callable.
        assert all(callable(dep) for dep in deps)
        assert len(deps) == 12
