"""Phase 19 Plan 13 — unit tests for get_db + chained provider factories.

Locks the D2 lifecycle (CONTEXT.md): ONE Session per HTTP request, closed
in `get_db`'s `finally`. Repository factories chain off `Depends(get_db)`;
service factories chain off either repo providers or singletons from
`app.core.services` (Plan 02 lru-cached factories).

Pure unit tests — no FastAPI app, no TestClient. SessionLocal is monkey-
patched to a fake so we count exactly one `.close()` per generator
exhaustion (Test 2) and one per exception path (Test 3). Tests 4-5 assert
factory wiring shape: returned object holds the supplied session/repo.
Test 6 is the structural invariant — no helper reaches into the legacy
`_container` (which is gone in Plan 13 — file-level greppable invariant).

Tiger-style: assertions at boundaries (pre-call invariant + post-call
state); flat early returns; self-explanatory names.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from app.api import dependencies as deps_module


# ---------------------------------------------------------------------------
# Test 1: get_db is a generator and yields a Session-shaped object
# ---------------------------------------------------------------------------


def test_get_db_is_generator_yielding_session(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = MagicMock(name="FakeSession")
    fake_session_local = MagicMock(name="SessionLocal", return_value=fake_session)
    monkeypatch.setattr(deps_module, "SessionLocal", fake_session_local)

    gen = deps_module.get_db()
    assert inspect.isgenerator(gen), "get_db must be a generator"

    # First next() yields the session — boundary assert pre-close
    yielded = next(gen)
    assert yielded is fake_session
    fake_session.close.assert_not_called()

    # Closing the generator triggers the finally — boundary assert post-close
    gen.close()
    fake_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: Iterating to exhaustion calls close exactly once
# ---------------------------------------------------------------------------


def test_get_db_calls_close_exactly_once_on_normal_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = MagicMock(name="FakeSession")
    monkeypatch.setattr(
        deps_module, "SessionLocal", MagicMock(return_value=fake_session),
    )

    gen = deps_module.get_db()
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)

    assert fake_session.close.call_count == 1


# ---------------------------------------------------------------------------
# Test 3: Exception during iteration still triggers session.close
# ---------------------------------------------------------------------------


def test_get_db_closes_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = MagicMock(name="FakeSession")
    monkeypatch.setattr(
        deps_module, "SessionLocal", MagicMock(return_value=fake_session),
    )

    gen = deps_module.get_db()
    next(gen)
    with pytest.raises(RuntimeError, match="boom"):
        gen.throw(RuntimeError("boom"))

    fake_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: repository factories return a repo bound to the supplied session
# ---------------------------------------------------------------------------


def test_get_user_repository_binds_session() -> None:
    fake_session = MagicMock(name="FakeSession")
    repo = deps_module.get_user_repository(fake_session)
    # SQLAlchemyUserRepository stores the session as `.session` attr
    assert getattr(repo, "session", None) is fake_session


def test_get_api_key_repository_binds_session() -> None:
    fake_session = MagicMock(name="FakeSession")
    repo = deps_module.get_api_key_repository(fake_session)
    assert getattr(repo, "session", None) is fake_session


def test_get_rate_limit_repository_binds_session() -> None:
    fake_session = MagicMock(name="FakeSession")
    repo = deps_module.get_rate_limit_repository(fake_session)
    assert getattr(repo, "session", None) is fake_session


def test_get_task_repository_binds_session() -> None:
    fake_session = MagicMock(name="FakeSession")
    repo = deps_module.get_task_repository(fake_session)
    assert getattr(repo, "session", None) is fake_session


def test_get_device_fingerprint_repository_binds_session() -> None:
    fake_session = MagicMock(name="FakeSession")
    repo = deps_module.get_device_fingerprint_repository(fake_session)
    assert getattr(repo, "session", None) is fake_session


# ---------------------------------------------------------------------------
# Test 5: service factories wire injected repo + singleton services
# ---------------------------------------------------------------------------


def test_get_auth_service_wires_repo_and_singletons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_user_repo = MagicMock(name="FakeUserRepo")
    fake_password = MagicMock(name="FakePasswordService")
    fake_token = MagicMock(name="FakeTokenService")

    monkeypatch.setattr(
        "app.core.services.get_password_service",
        lambda: fake_password,
    )
    monkeypatch.setattr(
        "app.core.services.get_token_service",
        lambda: fake_token,
    )

    service = deps_module.get_auth_service(fake_user_repo)

    assert service.user_repository is fake_user_repo
    assert service.password_service is fake_password
    assert service.token_service is fake_token


def test_get_key_service_wires_repo() -> None:
    fake_repo = MagicMock(name="FakeApiKeyRepo")
    service = deps_module.get_key_service(fake_repo)
    assert service.repository is fake_repo


def test_get_rate_limit_service_wires_repo() -> None:
    fake_repo = MagicMock(name="FakeRateLimitRepo")
    service = deps_module.get_rate_limit_service(fake_repo)
    assert service.repository is fake_repo


def test_get_free_tier_gate_wires_rate_limit_service() -> None:
    fake_rls = MagicMock(name="FakeRateLimitService")
    gate = deps_module.get_free_tier_gate(fake_rls)
    assert gate.rate_limit_service is fake_rls


def test_get_usage_event_writer_binds_session() -> None:
    fake_session = MagicMock(name="FakeSession")
    writer = deps_module.get_usage_event_writer(fake_session)
    assert writer.session is fake_session


def test_get_account_service_binds_session_and_repo() -> None:
    fake_session = MagicMock(name="FakeSession")
    fake_repo = MagicMock(name="FakeUserRepo")
    service = deps_module.get_account_service(fake_session, fake_repo)
    # AccountService stores session + lazily uses user_repository if supplied
    assert service.session is fake_session
    # Plan 15-03 deviation: service exposes _user_repository when explicit
    assert getattr(service, "_user_repository", None) is fake_repo


# ---------------------------------------------------------------------------
# Test 6: Helpers do NOT touch the legacy _container (file-level invariant)
# ---------------------------------------------------------------------------


_HELPER_NAMES = (
    "get_db",
    "get_user_repository",
    "get_api_key_repository",
    "get_rate_limit_repository",
    "get_task_repository",
    "get_device_fingerprint_repository",
    "get_auth_service",
    "get_key_service",
    "get_rate_limit_service",
    "get_free_tier_gate",
    "get_usage_event_writer",
    "get_account_service",
)


def test_helpers_never_touch_legacy_container() -> None:
    for name in _HELPER_NAMES:
        fn = getattr(deps_module, name)
        source = inspect.getsource(fn)
        assert "_container" not in source, (
            f"{name} must not reference the legacy _container global"
        )
