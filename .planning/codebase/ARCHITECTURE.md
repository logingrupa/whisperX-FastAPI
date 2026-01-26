# Architecture

**Analysis Date:** 2026-01-27

## Pattern Overview

**Overall:** Domain-Driven Design with Layered Architecture and Dependency Injection

**Key Characteristics:**
- Clean separation between business logic (domain) and infrastructure concerns
- Protocol-based interfaces using structural typing (Python's typing.Protocol)
- Dependency injection via dependency_injector container
- Background task processing with FastAPI's BackgroundTasks
- Async/await throughout HTTP layer

## Layers

**API Layer (HTTP & Request Handling):**
- Purpose: Expose FastAPI REST endpoints, handle HTTP concerns, validation, and dependency injection
- Location: `app/api/`
- Contains: Route handlers (`*_api.py`), request/response mappers, exception handlers, dependency providers
- Depends on: Services layer, domain entities, schemas
- Used by: External clients via HTTP

**Services Layer (Business Logic & Orchestration):**
- Purpose: Coordinate domain services, handle ML processing workflows, manage file operations
- Location: `app/services/`
- Contains: `TaskManagementService` (task CRUD), `FileService` (file operations), audio processing functions
- Depends on: Domain layer (entities, interfaces), infrastructure layer (database, ML models)
- Used by: API layer via dependency injection

**Domain Layer (Business Rules):**
- Purpose: Define core business entities and interfaces independent of any implementation
- Location: `app/domain/`
- Contains:
  - `entities/`: Pure Python dataclasses (Task) with business logic methods
  - `repositories/`: Protocol interfaces defining repository contracts
  - `services/`: Protocol interfaces for ML services (ITranscriptionService, IDiarizationService, etc.)
- Depends on: Nothing (no outbound dependencies)
- Used by: Services and infrastructure layers

**Infrastructure Layer (Technical Details):**
- Purpose: Implement domain interfaces using concrete technologies
- Location: `app/infrastructure/`
- Sub-layers:
  - `database/`: SQLAlchemy models, repositories, mappers, connection management
  - `ml/`: WhisperX service implementations (transcription, alignment, diarization, speaker assignment)
- Depends on: Domain layer (interfaces), external libraries (SQLAlchemy, WhisperX, PyTorch)
- Used by: Services layer

**Core Layer (Cross-Cutting Concerns):**
- Purpose: Configuration, logging, exception handling, dependency injection
- Location: `app/core/`
- Contains: Settings, container, custom exceptions, logging setup
- Depends on: External configuration tools (pydantic_settings)
- Used by: All layers

## Data Flow

**Speech-to-Text Processing Flow:**

1. **Request Entry** → `/speech-to-text` POST endpoint in `app/api/audio_api.py`
2. **Validation** → FileService validates extension, audio processing
3. **Task Creation** → Domain Task entity created with parameters
4. **Persistence** → Task saved to database via repository
5. **Background Queue** → Task scheduled in background via `BackgroundTasks`
6. **Processing** → `process_audio_common()` orchestrates ML pipeline:
   - Transcription via WhisperXTranscriptionService
   - Alignment via WhisperXAlignmentService
   - Diarization via WhisperXDiarizationService
   - Speaker assignment via WhisperXSpeakerAssignmentService
7. **Result Storage** → Task updated with result via repository
8. **Callback** → Result POSTed to callback_url if provided
9. **Response** → Immediate response returned with task identifier

**URL Processing Flow:**

Similar to above but with step 2 replaced by `FileService.download_from_url()` which handles HTTP download.

**State Management:**

- Task state progression: `processing` → `completed` or `failed`
- State stored in SQLite database via SQLAlchemy ORM
- Status updates via `repository.update()` method
- In-memory ML models cached in DI container as Singletons (never recreated)

## Key Abstractions

**Task Entity** (`app/domain/entities/task.py`):
- Purpose: Represent a processing job with all metadata and state
- Methods: `mark_as_completed()`, `mark_as_failed()`, status checks (`is_processing()`)
- Pattern: Dataclass with explicit state transition methods

**ITaskRepository** (`app/domain/repositories/task_repository.py`):
- Purpose: Abstract data access to Task storage
- Pattern: Protocol-based interface (structural typing)
- Implementation: `SQLAlchemyTaskRepository` in `app/infrastructure/database/repositories/`

**ML Service Interfaces** (`app/domain/services/*`):
- `ITranscriptionService`: Audio → Transcription
- `IDiarizationService`: Audio → Speaker segments
- `IAlignmentService`: Transcription + Audio → Time-aligned transcript
- `ISpeakerAssignmentService`: Transcript + Speaker info → Combined result
- Pattern: All Protocol-based interfaces with WhisperX implementations

**File Service** (`app/services/file_service.py`):
- Purpose: Isolate file I/O and validation logic
- Methods: `validate_file_extension()`, `save_upload()`, `download_from_url()`, `secure_filename()`
- Pattern: Stateless singleton service with static utility methods

## Entry Points

**Application Entry Point:**
- Location: `app/main.py`
- Creates FastAPI app with lifespan context manager
- Initializes dependency injection container
- Registers API routers and exception handlers
- Runs database migrations on startup

**API Endpoints:**
- `POST /speech-to-text`: Upload file for transcription
- `POST /speech-to-text-url`: Transcribe from URL
- `GET /tasks/{identifier}`: Get task status and results
- `GET /tasks`: List all tasks
- `GET /health*`: Health checks (live, ready, simple)

**Background Task Entry:**
- Location: `app/services/audio_processing_service.py::process_audio_task()`
- Scheduled via FastAPI `BackgroundTasks.add_task()`
- Handles full ML pipeline with error handling and callbacks

## Error Handling

**Strategy:** Exception hierarchy with specific handlers and HTTP status codes

**Patterns:**

Exception hierarchy in `app/core/exceptions.py`:
- `DomainError`: Business logic violations
- `ValidationError`: Input validation failures (400)
- `FileValidationError`: File extension/format issues (400)
- `DatabaseOperationError`: Data persistence failures (500)
- `TaskNotFoundError`: Missing task queries (404)
- `InfrastructureError`: ML processing failures (500)
- `TranscriptionFailedError`: Specific ML operation failures (500)

Exception handlers registered in main.py map exceptions to HTTP responses:
- `task_not_found_handler`: Returns 404
- `validation_error_handler`: Returns 400
- `domain_error_handler`: Returns 422
- `infrastructure_error_handler`: Returns 500
- `generic_error_handler`: Returns 500 for unexpected errors

Database operations rollback on failure via SQLAlchemy session management.

## Cross-Cutting Concerns

**Logging:**
- Framework: Python's `logging` module with custom `logger` in `app/core/logging.py`
- Used throughout: Debug/info/warning/error at key decision points
- Format: Structured text with timestamps and level indicators

**Validation:**
- API layer: Pydantic schemas (`app/api/schemas/task_schemas.py`)
- File validation: FileService methods check extensions against Config
- Language validation: `validate_language_code()` checks against WhisperX language set
- Model parameters: Pydantic Field validators ensure valid device/compute types

**Authentication:**
- Currently: None implemented (API is open)
- Infrastructure present: Callback URL validation to prevent SSRF attacks

**Dependency Injection:**
- Container: `app/core/container.py` using dependency_injector
- Wiring: Explicit wiring in main.py → `dependencies.set_container()`
- Injection: FastAPI Depends() in route parameters
- Lifecycle: Singletons for stateless services and config; Factories for stateful services with sessions

---

*Architecture analysis: 2026-01-27*
