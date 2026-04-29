"""Dependency injection container for managing application dependencies."""

from dependency_injector import containers, providers

from app.core.config import get_settings
from app.infrastructure.database.connection import SessionLocal, engine
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from app.infrastructure.ml import (
    WhisperXAlignmentService,
    WhisperXDiarizationService,
    WhisperXSpeakerAssignmentService,
    WhisperXTranscriptionService,
)
from app.services.file_service import FileService
from app.services.task_management_service import TaskManagementService

# Phase 11 — auth repositories
from app.infrastructure.database.repositories.sqlalchemy_api_key_repository import (
    SQLAlchemyApiKeyRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_device_fingerprint_repository import (
    SQLAlchemyDeviceFingerprintRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)

# Phase 11 — auth services
from app.services.auth import (
    AuthService,
    CsrfService,
    KeyService,
    PasswordService,
    RateLimitService,
    TokenService,
)

# Phase 13 — WS ticket service (single-use 60s WebSocket auth, MID-06)
from app.services.ws_ticket_service import WsTicketService

# Phase 13-08 — free-tier gate + usage event writer (RATE-01..12, BILL-01)
from app.services.free_tier_gate import FreeTierGate
from app.services.usage_event_writer import UsageEventWriter


class Container(containers.DeclarativeContainer):
    """
    Dependency injection container for application services.

    This container manages the lifecycle and dependencies of all application
    components including configuration, database connections, repositories,
    services, and ML models.

    Architecture:
        - Configuration: Singleton settings instance
        - Database: Singleton engine, factory sessions
        - Repositories: Factory instances with session dependencies
        - Services: Mix of singletons (stateless) and factories (stateful)
        - ML Services: Singletons for model caching and reuse

    Lifecycle Management:
        - Singleton: Created once and reused (Config, FileService, ML Services)
        - Factory: New instance per request (Services with database sessions)
        - Resource: Managed lifecycle with init/cleanup (Database connections)

    Example:
        >>> container = Container()
        >>> container.wire(modules=["app.api.dependencies"])
        >>> # Services are now available via dependency injection
        >>> # Clean up on shutdown
        >>> container.unwire()
    """

    # Configuration - Singleton for application settings
    config = providers.Singleton(get_settings)

    # Database - Singleton engine, factory for sessions
    db_engine = providers.Singleton(lambda: engine)
    db_session_factory = providers.Factory(SessionLocal)

    # Repositories - Factory pattern with session dependency
    task_repository = providers.Factory(
        SQLAlchemyTaskRepository,
        session=db_session_factory,
    )

    # Services - Stateless services are singletons
    file_service = providers.Singleton(FileService)

    # Services - Stateful services are factories
    task_management_service = providers.Factory(
        TaskManagementService,
        repository=task_repository,
    )

    # ---------------------------------------------------------------
    # Phase 11 — Auth repositories (Factory pattern, session injected)
    # ---------------------------------------------------------------
    user_repository = providers.Factory(
        SQLAlchemyUserRepository,
        session=db_session_factory,
    )
    api_key_repository = providers.Factory(
        SQLAlchemyApiKeyRepository,
        session=db_session_factory,
    )
    rate_limit_repository = providers.Factory(
        SQLAlchemyRateLimitRepository,
        session=db_session_factory,
    )
    device_fingerprint_repository = providers.Factory(
        SQLAlchemyDeviceFingerprintRepository,
        session=db_session_factory,
    )

    # ---------------------------------------------------------------
    # Phase 11 — Auth services (Singletons for stateless, Factories for stateful)
    # ---------------------------------------------------------------
    password_service = providers.Singleton(PasswordService)
    csrf_service = providers.Singleton(CsrfService)
    token_service = providers.Singleton(
        TokenService,
        secret=config.provided.auth.JWT_SECRET.provided.get_secret_value.call(),
    )
    auth_service = providers.Factory(
        AuthService,
        user_repository=user_repository,
        password_service=password_service,
        token_service=token_service,
    )
    key_service = providers.Factory(
        KeyService,
        repository=api_key_repository,
    )
    rate_limit_service = providers.Factory(
        RateLimitService,
        repository=rate_limit_repository,
    )

    # ---------------------------------------------------------------
    # Phase 13 — WS ticket service (in-memory; Singleton)
    #
    # Singleton lifecycle is REQUIRED — the in-memory dict must persist
    # across requests. A Factory would create a new dict per request,
    # defeating the ticket store.
    # ---------------------------------------------------------------
    ws_ticket_service = providers.Singleton(WsTicketService)

    # ---------------------------------------------------------------
    # Phase 13-08 — Free-tier gate + usage event writer (RATE-01..12, BILL-01)
    #
    # Both Factory: each request resolves a fresh instance bound to a
    # fresh DB session (UsageEventWriter) / fresh RateLimitService
    # (FreeTierGate). The shared state lives in SQLite buckets, not in
    # the service instance.
    # ---------------------------------------------------------------
    free_tier_gate = providers.Factory(
        FreeTierGate,
        rate_limit_service=rate_limit_service,
    )
    usage_event_writer = providers.Factory(
        UsageEventWriter,
        session=db_session_factory,
    )

    # ML Services - Singletons for model caching and reuse
    # These services load heavy ML models and should be reused
    transcription_service = providers.Singleton(
        WhisperXTranscriptionService,
    )

    diarization_service = providers.Singleton(
        WhisperXDiarizationService,
        hf_token=config.provided.whisper.HF_TOKEN,
    )

    alignment_service = providers.Singleton(
        WhisperXAlignmentService,
    )

    speaker_assignment_service = providers.Singleton(
        WhisperXSpeakerAssignmentService,
    )
