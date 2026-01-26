# Codebase Structure

**Analysis Date:** 2026-01-27

## Directory Layout

```
whisperx/
├── app/                             # Main application package
│   ├── api/                         # HTTP API layer (FastAPI routers)
│   │   ├── audio_api.py             # Speech-to-text endpoints
│   │   ├── task_api.py              # Task management endpoints
│   │   ├── audio_services_api.py    # Individual service endpoints
│   │   ├── callbacks.py             # Webhook callback handlers
│   │   ├── exception_handlers.py    # HTTP error handlers
│   │   ├── dependencies.py          # FastAPI dependency injection
│   │   ├── constants.py             # API constants
│   │   ├── mappers/                 # Request/response mappers
│   │   │   └── task_mapper.py       # Task DTO transformations
│   │   └── schemas/                 # Pydantic request/response schemas
│   │       └── task_schemas.py      # Task-related schemas
│   │
│   ├── core/                        # Cross-cutting concerns
│   │   ├── config.py                # Pydantic settings (database, whisper, logging)
│   │   ├── container.py             # Dependency injection container
│   │   ├── exceptions.py            # Custom exception classes
│   │   ├── logging.py               # Logging configuration
│   │   └── warnings_filter.py       # Library warning suppression
│   │
│   ├── domain/                      # Business logic layer (DDD)
│   │   ├── entities/                # Core business entities
│   │   │   └── task.py              # Task entity with business methods
│   │   ├── repositories/            # Data access interfaces
│   │   │   └── task_repository.py   # ITaskRepository protocol
│   │   └── services/                # Service interfaces
│   │       ├── transcription_service.py    # ITranscriptionService
│   │       ├── alignment_service.py        # IAlignmentService
│   │       ├── diarization_service.py      # IDiarizationService
│   │       └── speaker_assignment_service.py # ISpeakerAssignmentService
│   │
│   ├── infrastructure/              # Technical implementation layer
│   │   ├── database/                # Database/persistence
│   │   │   ├── models.py            # SQLAlchemy ORM models
│   │   │   ├── connection.py        # Database connection setup
│   │   │   ├── unit_of_work.py      # UoW pattern (if used)
│   │   │   ├── mappers/             # ORM↔Domain mappers
│   │   │   │   └── task_mapper.py   # ORMTask ↔ DomainTask
│   │   │   └── repositories/        # Repository implementations
│   │   │       └── sqlalchemy_task_repository.py # ITaskRepository impl
│   │   │
│   │   └── ml/                      # ML service implementations
│   │       ├── whisperx_transcription_service.py
│   │       ├── whisperx_alignment_service.py
│   │       ├── whisperx_diarization_service.py
│   │       └── whisperx_speaker_assignment_service.py
│   │
│   ├── services/                    # Business orchestration layer
│   │   ├── task_management_service.py       # Task CRUD operations
│   │   ├── file_service.py                  # File upload/download handling
│   │   ├── audio_processing_service.py      # ML pipeline orchestration
│   │   └── whisperx_wrapper_service.py      # WhisperX model operations
│   │
│   ├── main.py                      # FastAPI app initialization
│   ├── schemas.py                   # Pydantic models (requests/responses)
│   ├── audio.py                     # Audio processing utilities
│   ├── files.py                     # File extension constants
│   ├── callbacks.py                 # Callback/webhook utilities
│   ├── transcript.py                # Transcript formatting utilities
│   └── docs.py                      # Documentation generation
│
├── tests/                           # Test suite
│   ├── unit/                        # Unit tests
│   │   ├── api/                     # API route tests
│   │   ├── core/                    # Config/exception tests
│   │   ├── domain/                  # Entity/interface tests
│   │   └── infrastructure/          # Repository/DB tests
│   ├── integration/                 # Integration tests
│   ├── e2e/                         # End-to-end tests
│   ├── fixtures/                    # pytest fixtures
│   ├── factories/                   # Test data factories (factory-boy)
│   ├── mocks/                       # Mock implementations
│   └── test_files/                  # Sample audio files for testing
│
├── docs/                            # Documentation
│   └── architecture/                # Architecture diagrams
│
├── scripts/                         # Utility scripts
│
├── pyproject.toml                   # Project metadata and dependencies
├── pytest.toml                      # pytest configuration
├── .env                             # Environment variables
├── .env.example                     # Example environment template
├── dockerfile                       # Docker container definition
└── docker-compose.yml               # Docker Compose setup
```

## Directory Purposes

**`app/api/`:**
- Purpose: FastAPI routes, HTTP concerns, dependency injection wiring
- Contains: Endpoint handlers, schemas, mappers, exception handlers, dependencies
- Key files: `audio_api.py` (main endpoints), `dependencies.py` (DI setup)

**`app/core/`:**
- Purpose: Application-wide configuration and infrastructure
- Contains: Settings loader, DI container, exception definitions, logging setup
- Key files: `config.py` (Pydantic settings), `container.py` (dependency_injector)

**`app/domain/`:**
- Purpose: Business logic independent of frameworks
- Contains: Entities, repository interfaces, service interfaces
- Pattern: Protocol-based interfaces (Python structural typing)
- Key files: `entities/task.py`, `repositories/task_repository.py`

**`app/infrastructure/`:**
- Purpose: Concrete implementations of interfaces using external libraries
- Sub-paths:
  - `database/`: SQLAlchemy ORM, database operations
  - `ml/`: WhisperX ML service implementations
- Key files: `database/models.py` (SQLAlchemy), `ml/*.py` (service impls)

**`app/services/`:**
- Purpose: Business logic orchestration and use cases
- Contains: Services that coordinate domain + infrastructure layers
- Lifecycle: Singletons for stateless (FileService), Factories for stateful (TaskManagementService)
- Key files: `audio_processing_service.py`, `task_management_service.py`

**`tests/`:**
- Purpose: Test suite organized by layer
- Contains: Unit tests (mocked), integration tests (real DB), e2e tests (full API)
- Patterns: pytest with markers (unit, integration, e2e, slow)
- Key dirs: `fixtures/` (test setup), `factories/` (test data), `mocks/` (stubs)

## Key File Locations

**Entry Points:**
- `app/main.py`: FastAPI app creation, container setup, route registration

**Configuration:**
- `app/core/config.py`: Environment-based settings via Pydantic
- `app/core/container.py`: Dependency injection container setup
- `pyproject.toml`: Project metadata, dependencies, tool configs

**Core Logic:**
- `app/domain/entities/task.py`: Task business entity with state methods
- `app/services/audio_processing_service.py`: ML pipeline orchestration
- `app/services/file_service.py`: File validation and I/O

**Database:**
- `app/infrastructure/database/models.py`: SQLAlchemy ORM models
- `app/infrastructure/database/repositories/sqlalchemy_task_repository.py`: Repository impl
- `app/infrastructure/database/mappers/task_mapper.py`: ORMTask ↔ DomainTask conversion

**ML Services:**
- `app/infrastructure/ml/whisperx_transcription_service.py`: Transcription
- `app/infrastructure/ml/whisperx_alignment_service.py`: Word-level alignment
- `app/infrastructure/ml/whisperx_diarization_service.py`: Speaker detection
- `app/infrastructure/ml/whisperx_speaker_assignment_service.py`: Match speakers to words

**Testing:**
- `tests/unit/`: Fast, fully mocked tests per layer
- `tests/integration/`: Database and real service tests
- `tests/e2e/`: Full API integration tests

## Naming Conventions

**Files:**
- Python modules: `snake_case.py`
- API routers: `*_api.py` (e.g., `audio_api.py`, `task_api.py`)
- Services: `*_service.py` (e.g., `file_service.py`, `task_management_service.py`)
- Mappers: `*_mapper.py` (e.g., `task_mapper.py`)
- Models: `models.py` for ORM, `*_model.py` for individual models
- Tests: `test_*.py` for pytest discovery

**Directories:**
- Layer folders: `lowercase` (api, core, domain, infrastructure, services)
- Sub-layers: `lowercase` (database, ml, repositories, entities)
- Test folders: `unit/`, `integration/`, `e2e/`, `fixtures/`, `factories/`, `mocks/`, `test_files/`

**Classes:**
- Entities: `TaskName` (e.g., Task)
- Services: `TaskNameService` (e.g., FileService, TaskManagementService)
- ML implementations: `WhisperX*Service` (e.g., WhisperXTranscriptionService)
- Interfaces: `ITaskName` (Protocol pattern, e.g., ITaskRepository)
- ORM models: PascalCase (e.g., Task for `tasks` table)

**Functions:**
- camelCase or snake_case: snake_case used throughout
- Utility functions: `_helper()` prefix for private functions
- Processing functions: `process_*()` (e.g., `process_audio_file()`, `process_audio_task()`)
- Validation functions: `validate_*()` (e.g., `validate_language_code()`)

## Where to Add New Code

**New API Endpoint:**
- File: `app/api/{feature}_api.py` (create if new feature)
- Schemas: Add to `app/api/schemas/task_schemas.py` or new `app/api/schemas/{feature}_schemas.py`
- Route handler: Use `@router.post()` or `@router.get()` with FastAPI patterns
- Dependencies: Add to `app/api/dependencies.py` or inline with Depends()
- Tests: Add test class to `tests/unit/api/test_{feature}_api.py`

**New Service:**
- Implementation: `app/services/{feature}_service.py`
- Interface: If needed, add Protocol to `app/domain/services/{feature}_service.py`
- Registration: Add to `app/core/container.py` (Singleton or Factory)
- Export: Add to `app/services/__init__.py`
- Tests: Add test class to `tests/unit/test_{feature}_service.py`

**New Domain Entity:**
- Entity class: `app/domain/entities/{entity_name}.py`
- Repository interface: `app/domain/repositories/{entity_name}_repository.py`
- ORM model: Add to `app/infrastructure/database/models.py`
- Mapper: `app/infrastructure/database/mappers/{entity_name}_mapper.py`
- Repository impl: `app/infrastructure/database/repositories/sqlalchemy_{entity_name}_repository.py`

**New ML Service Integration:**
- Interface: `app/domain/services/{service_name}_service.py` with Protocol
- Implementation: `app/infrastructure/ml/{provider}_{service_name}_service.py`
- Registration: Add to `app/infrastructure/ml/__init__.py` and container
- Export: Add to `app/infrastructure/ml/__init__.py`

**Tests:**
- Unit tests: `tests/unit/{layer}/test_{module}.py` (all deps mocked)
- Integration tests: `tests/integration/test_{feature}.py` (real DB)
- E2E tests: `tests/e2e/test_{endpoint}.py` (full API)
- Fixtures: `tests/fixtures/{resource}_fixtures.py`
- Test data: `tests/factories/{entity}_factory.py` (factory-boy)

## Special Directories

**`app/core/`:**
- Purpose: Framework and cross-cutting setup
- Generated: No
- Committed: Yes
- Contents: Settings, DI container, exceptions, logging

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes
- Committed: No
- Managed by: `uv` package manager

**`tests/test_files/`:**
- Purpose: Sample audio/video files for testing
- Generated: No (committed)
- Committed: Yes (small test files)
- Usage: Loaded by test fixtures

**`records.db`:**
- Purpose: SQLite database file (development/testing)
- Generated: Yes (created on first run)
- Committed: No
- Connection: `sqlite:///records.db` from Config

---

*Structure analysis: 2026-01-27*
