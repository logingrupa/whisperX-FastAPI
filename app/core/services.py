"""Module-level lru-cached singleton factories for stateless services.

Phase 19 Plan 02 (T-19-02). Replaces the `dependency_injector` Singleton/
Factory providers in `app/core/container.py` for stateless services. Plans
03..12 incrementally rewire callsites; this plan only adds the new module
so existing `Container` keeps working.

Decision lock (19-RESEARCH §Q3): functools.lru_cache over bare module
globals — gives lazy init for ML services AND a `cache_clear()` handle
for test teardown (19-PATTERNS Pitfall 7).

Tiger-style:
- one factory per service, no nested helpers
- no `if`/early-return inside factories — they are one-line constructors
- module-top imports for non-ML services (lazy only for ML — keeps CLI /
  migration paths free of model-load side effects)
- self-explanatory factory names (`get_<service>_service`)

Singleton invariants verified by tests/unit/test_services_module.py.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.auth.csrf_service import CsrfService
from app.services.auth.password_service import PasswordService
from app.services.auth.token_service import TokenService
from app.services.file_service import FileService
from app.services.ws_ticket_service import WsTicketService


# ---------------------------------------------------------------------------
# Stateless auth services
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_password_service() -> PasswordService:
    """Return the process-wide PasswordService singleton."""
    return PasswordService()


@lru_cache(maxsize=1)
def get_csrf_service() -> CsrfService:
    """Return the process-wide CsrfService singleton."""
    return CsrfService()


@lru_cache(maxsize=1)
def get_token_service() -> TokenService:
    """Return the process-wide TokenService singleton (JWT secret bound at first call)."""
    return TokenService(
        secret=get_settings().auth.JWT_SECRET.get_secret_value(),
    )


# ---------------------------------------------------------------------------
# Stateful in-process services
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_ws_ticket_service() -> WsTicketService:
    """Return the process-wide WsTicketService singleton (in-memory ticket store)."""
    return WsTicketService()


@lru_cache(maxsize=1)
def get_file_service() -> FileService:
    """Return the process-wide FileService singleton."""
    return FileService()


# ---------------------------------------------------------------------------
# ML services — lazy import inside factory body
#
# Importing whisperx / pyannote / torch at module load adds ~3s and pulls
# CUDA. CLI commands and Alembic migrations have no need for ML; deferring
# the import to first factory call keeps non-ML paths fast (19-RESEARCH
# Open Question 1).
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_transcription_service():
    """Return the process-wide WhisperXTranscriptionService singleton (lazy ML import)."""
    from app.infrastructure.ml import WhisperXTranscriptionService

    return WhisperXTranscriptionService()


@lru_cache(maxsize=1)
def get_alignment_service():
    """Return the process-wide WhisperXAlignmentService singleton (lazy ML import)."""
    from app.infrastructure.ml import WhisperXAlignmentService

    return WhisperXAlignmentService()


@lru_cache(maxsize=1)
def get_diarization_service():
    """Return the process-wide WhisperXDiarizationService singleton (lazy ML import).

    HuggingFace token bound at first call from `settings.whisper.HF_TOKEN`.
    """
    from app.infrastructure.ml import WhisperXDiarizationService

    return WhisperXDiarizationService(hf_token=get_settings().whisper.HF_TOKEN)


@lru_cache(maxsize=1)
def get_speaker_assignment_service():
    """Return the process-wide WhisperXSpeakerAssignmentService singleton (lazy ML import)."""
    from app.infrastructure.ml import WhisperXSpeakerAssignmentService

    return WhisperXSpeakerAssignmentService()
