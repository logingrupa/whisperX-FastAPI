"""Unit tests for app.core.services — module-level @lru_cache singleton invariant.

Phase 19 Plan 02 (T-19-02). Locks the D1 replacement pattern: every stateless
service exposed as a `@lru_cache(maxsize=1)` factory in `app/core/services.py`.

Invariants asserted:
1. Repeated calls return the SAME instance (`is` identity).
2. ML factories never trigger module-load of PyTorch/whisperx (lazy import
   inside the function body — verified by patching the lazy-imported symbol
   on the source module BEFORE the factory runs).
3. `cache_clear()` handle is exposed (test isolation per 19-PATTERNS Pitfall 7).
"""

from __future__ import annotations

from unittest.mock import patch

from app.core import services


def _clear_all_caches() -> None:
    """Test isolation — clear every singleton between tests."""
    services.get_password_service.cache_clear()
    services.get_csrf_service.cache_clear()
    services.get_token_service.cache_clear()
    services.get_ws_ticket_service.cache_clear()
    services.get_file_service.cache_clear()
    services.get_transcription_service.cache_clear()
    services.get_alignment_service.cache_clear()
    services.get_diarization_service.cache_clear()
    services.get_speaker_assignment_service.cache_clear()


def test_get_password_service_is_singleton() -> None:
    _clear_all_caches()
    first = services.get_password_service()
    second = services.get_password_service()
    assert first is second


def test_get_csrf_service_is_singleton() -> None:
    _clear_all_caches()
    first = services.get_csrf_service()
    second = services.get_csrf_service()
    assert first is second


def test_get_token_service_is_singleton_and_reads_secret_lazily() -> None:
    _clear_all_caches()
    # Identity invariant.
    first = services.get_token_service()
    second = services.get_token_service()
    assert first is second
    # Secret is read at first invocation (TokenService stores secret on self).
    assert first.secret  # truthy non-empty string


def test_get_ws_ticket_service_is_singleton_with_shared_dict() -> None:
    _clear_all_caches()
    instance_a = services.get_ws_ticket_service()
    instance_b = services.get_ws_ticket_service()
    assert instance_a is instance_b
    # Functional proof: a ticket issued via instance_a is consumable via
    # instance_b — they MUST share the in-memory dict.
    token, _expires = instance_a.issue(user_id=42, task_id="task-abc")
    consumed_user_id = instance_b.consume(token, "task-abc")
    assert consumed_user_id == 42


def test_get_file_service_is_singleton() -> None:
    _clear_all_caches()
    first = services.get_file_service()
    second = services.get_file_service()
    assert first is second


def test_cache_clear_handle_invalidates_singleton() -> None:
    _clear_all_caches()
    first = services.get_password_service()
    services.get_password_service.cache_clear()
    second = services.get_password_service()
    assert first is not second


def test_ml_factories_are_lru_cache_wrapped_and_lazy() -> None:
    """ML factories MUST expose cache_clear (lru_cache) AND must NOT
    construct the heavy PyTorch model at module load — the import lives
    inside the factory body. Patch the symbol on the source module so
    the inside-function `from app.infrastructure.ml import X` resolves
    to the mock.
    """
    _clear_all_caches()
    # cache_clear handle present on every ML factory.
    assert hasattr(services.get_transcription_service, "cache_clear")
    assert hasattr(services.get_alignment_service, "cache_clear")
    assert hasattr(services.get_diarization_service, "cache_clear")
    assert hasattr(services.get_speaker_assignment_service, "cache_clear")

    # Patch the lazy-imported classes on their source module; the factory
    # body's `from app.infrastructure.ml import X` will resolve to the mock.
    with (
        patch("app.infrastructure.ml.WhisperXTranscriptionService") as transcription_cls,
        patch("app.infrastructure.ml.WhisperXAlignmentService") as alignment_cls,
        patch("app.infrastructure.ml.WhisperXDiarizationService") as diarization_cls,
        patch(
            "app.infrastructure.ml.WhisperXSpeakerAssignmentService"
        ) as speaker_cls,
    ):
        transcription = services.get_transcription_service()
        alignment = services.get_alignment_service()
        diarization = services.get_diarization_service()
        speaker = services.get_speaker_assignment_service()

        # Each factory invoked its mock (lazy import resolved to the patch).
        assert transcription is transcription_cls.return_value
        assert alignment is alignment_cls.return_value
        assert diarization is diarization_cls.return_value
        assert speaker is speaker_cls.return_value

        # Singleton invariant: second call returns the SAME mocked instance
        # (no second construction).
        assert services.get_transcription_service() is transcription
        assert transcription_cls.call_count == 1
