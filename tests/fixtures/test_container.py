"""Test container — DEPRECATED, deletion targeted in Phase 19 Plan 13.

Phase 19 Plan 10: this module is being phased out alongside the legacy
``app/core/container.py``. The 14 integration test fixtures previously
used ``Container().db_session_factory.override(...)`` + custom subclass
overrides; they migrated to ``app.dependency_overrides[get_db]`` in this
plan. The remaining importers
(``tests/fixtures/__init__.py``, ``tests/conftest.py``,
``tests/unit/core/test_container.py``) keep this stub callable so
collection succeeds at every commit between Plan 10 and Plan 13. Plan 13
``git rm``'s this file alongside ``app/core/container.py``.

Mock ML services are still wired here for the unit-level
``tests/unit/core/test_container.py`` cases that exercise the legacy
Container resolution surface; those cases are also queued for deletion
in Plan 13.
"""

from dependency_injector import providers
from sqlalchemy import create_engine

from app.core.container import Container
from tests.mocks import (
    MockAlignmentService,
    MockDiarizationService,
    MockSpeakerAssignmentService,
    MockTranscriptionService,
)


class TestContainer(Container):
    """Subclass of the legacy Container with mock ML services.

    DEPRECATED — this class is the last user of the legacy DI graph; once
    Plan 13 deletes ``app/core/container.py``, this subclass goes with it.
    """

    # Override database with in-memory SQLite for test isolation
    db_engine = providers.Singleton(
        create_engine,
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Override ML services with fast mocks (no GPU, no network calls)
    transcription_service = providers.Singleton(MockTranscriptionService)

    diarization_service = providers.Singleton(
        MockDiarizationService,
        hf_token="mock_token",
    )

    alignment_service = providers.Singleton(MockAlignmentService)

    speaker_assignment_service = providers.Singleton(MockSpeakerAssignmentService)

    # All other services (repositories, file service, task management) inherit from Container
    # and work normally with the test database
