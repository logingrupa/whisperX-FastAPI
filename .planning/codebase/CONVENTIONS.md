# Coding Conventions

**Analysis Date:** 2026-01-27

## Naming Patterns

**Files:**
- Snake_case for all Python modules: `audio_api.py`, `file_service.py`, `mock_transcription_service.py`
- Directories use snake_case: `app/api/`, `app/core/`, `app/domain/`
- Test files follow pattern: `test_*.py` (e.g., `test_health_endpoints.py`, `test_task_lifecycle.py`)
- Mock files follow pattern: `mock_*.py` (e.g., `mock_transcription_service.py`)

**Functions:**
- Snake_case for all function and method names: `speech_to_text()`, `validate_file_extension()`, `get_audio_duration()`
- Test functions start with `test_`: `test_health_check()`, `test_create_and_retrieve_task()`
- Helper methods use descriptive snake_case: `_default_result()`, `secure_filename()`, `is_processing()`
- Private/internal methods prefixed with single underscore: `_default_result()` in `MockTranscriptionService`

**Variables:**
- Snake_case for all variables: `audio_duration`, `task_params`, `file_extension`, `temp_file`
- Constants in UPPER_SNAKE_CASE: `ALLOWED_EXTENSIONS`, `AUDIO_FILE`, `TRANSCRIPT_RESULT_1`
- Boolean variables start with `is_` or `should_`: `is_processing()`, `should_fail`, `follow_redirects`

**Types and Classes:**
- PascalCase for class names: `Task`, `Response`, `FileService`, `MockTranscriptionService`, `TaskFactory`
- Pydantic BaseModel classes use PascalCase: `TaskSimple`, `Metadata`, `TranscriptionSegment`, `Segment`
- Dataclass entities use PascalCase: `@dataclass class Task`
- Exception classes use PascalCase: `ApplicationError`, `DomainError`, `ValidationError`, `TaskNotFoundError`
- API routers in snake_case: `stt_router`, `task_router`, `service_router`

## Code Style

**Formatting:**
- Tool: Ruff (with isort profile "black")
- Max line length: Enforced by pre-commit
- Mixed line endings converted to LF (Unix style)
- Trailing whitespace automatically removed
- End-of-file fixed with single newline

**Linting:**
- Tool: Ruff v0.14.11
- Pre-commit hook: `ruff-check` with `--fix` to auto-fix issues
- Comprehensive configuration with isort profile "black" for import sorting
- File patterns exclude migrations

**Type Checking:**
- Tool: mypy v1.19.1
- Strict mode enabled: `disallow_untyped_defs = true`, `disallow_incomplete_defs = true`
- Configuration file: `pyproject.toml` with `python_version = "3.11"`
- Ignores missing imports for external ML packages (whisperx, pyannote, torch, etc.)
- Enforces return type hints, catches unused ignores
- MyPy excluded from test files (exclude: `^tests/`)

## Import Organization

**Order:**
1. Standard library imports (`import os`, `import logging`, `from typing import Any`)
2. Third-party imports (`import fastapi`, `from pydantic import BaseModel`, `import numpy as np`)
3. Application imports (`from app.core.exceptions import ValidationError`)
4. Local module imports (`from .dependencies import get_file_service`)

**Path Aliases:**
- All imports use absolute paths from project root: `from app.api.dependencies import get_file_service`
- No relative imports: Use `from app.core.config import Config` not `from ...core.config`
- Organized in `pyproject.toml` with isort profile "black"

**Import Patterns:**
- Grouped imports from same module: `from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile`
- Comments allowed for organization (e.g., `# noqa: E402` for post-initialization imports in `main.py`)
- Conditional imports after setup: `load_dotenv()` runs before importing app modules in `main.py`

## Error Handling

**Exception Hierarchy:**
- All custom exceptions inherit from `ApplicationError` (defined in `app/core/exceptions.py`)
- Domain errors inherit from `DomainError` for business logic violations
- Infrastructure errors inherit from `InfrastructureError` for external system failures
- Validation errors inherit from `ValidationError` for input validation failures
- Each exception includes: `message`, `code`, `correlation_id`, `user_message`, and `details`

**Exception Pattern:**
```python
# Example from app/core/exceptions.py
raise TaskNotFoundError(identifier=str(uuid4()))

# Exceptions include safe user messages
def __init__(self, identifier: str, correlation_id: Optional[str] = None) -> None:
    super().__init__(
        message=f"Task with identifier '{identifier}' not found",
        code="TASK_NOT_FOUND",
        user_message="The requested task could not be found. Please check the task ID.",
        correlation_id=correlation_id,
        identifier=identifier,
    )
```

**Usage:**
- Raise domain-specific exceptions with context (e.g., `FileValidationError`, `AudioProcessingError`)
- Log exceptions before raising: `logger.warning("Invalid file extension for file %s", filename)`
- Catch broad exceptions and convert to domain exceptions: `except Exception: logging.exception(...)`
- All exceptions convertible to dict with `to_dict()` method for API responses

## Logging

**Framework:** Structured logging with `colorlog` for console output, yaml config for setup

**Logger Instance:**
- Use centralized logger from `app.core.logging`: `from app.core.logging import logger`
- Configure with `logger.info()`, `logger.warning()`, `logger.exception()`
- Never use bare `logging.basicConfig()` (found in `audio_api.py` line 46 - anti-pattern)

**Patterns:**
- Log at INFO level for major operations: `logger.info("Received file upload request: %s", file.filename)`
- Log at WARNING for validation failures: `logger.warning("Invalid file extension for file %s", filename)`
- Log exceptions with context: `logger.exception("Readiness check failed:")` captures full stack
- Include relevant IDs in logs: `logger.info("Task added to database: ID %s", identifier)`
- Use % formatting with separate args: `logger.info("Message: %s", value)` not f-strings

## Comments

**When to Comment:**
- Document WHY decisions were made, not WHAT the code does (code is self-documenting)
- Use comments for non-obvious business logic
- Example from `audio_api.py`: Comments explaining parameter validation and file processing steps

**DocString/TSDoc:**
- All public functions and classes require docstrings
- Format: Google-style with Args, Returns, Raises sections
- Example from `app/services/file_service.py`:
  ```python
  def validate_file_extension(filename: str, allowed_extensions: set[str]) -> str:
      """
      Validate that the file extension is in the allowed set.

      Args:
          filename: Name of the file to validate
          allowed_extensions: Set of allowed file extensions (e.g., {'.mp3', '.wav'})

      Returns:
          The validated file extension in lowercase

      Raises:
          HTTPException: If the file extension is not in the allowed set
      """
  ```

- All methods and classes documented: `"""Purpose of this class/function."""`
- Private methods also documented for maintainability
- Docstrings for dataclass attributes: Listed in class-level docstring

## Function Design

**Size:** Functions should be short and focused
- Average function length: 15-30 lines
- Maximum complexity: Handle single responsibility (e.g., validate or process, not both)
- Example: `secure_filename()` has single purpose - sanitize for filesystem

**Parameters:**
- Use type hints for all parameters and return values: `def process_audio(file: UploadFile) -> str:`
- Use dependency injection with FastAPI `Depends()`: `repository: ITaskRepository = Depends(get_task_repository)`
- Named parameters for complex operations (no long positional args)
- Default values in function signature when appropriate

**Return Values:**
- Always include explicit return type: `-> Response:`, `-> None:`, `-> str | None:`
- Use union types for optional returns: `str | None` (PEP 604 syntax, not `Optional[str]`)
- Return business objects (domain entities) not database models
- Consistent return structure (e.g., always Response with identifier and message)

## Module Design

**Exports:**
- Explicit `__init__.py` files for package imports
- Example from `app/api/__init__.py`: Imports and re-exports router and exceptions
- Makes public API clear: `from app.api import stt_router, task_router, service_router`

**Barrel Files:**
- Used strategically: `app/api/__init__.py`, `app/domain/repositories/__init__.py`
- Group related imports: `from app.core.exceptions import (DomainError, ValidationError, ...)`
- Reduces import nesting in consuming modules

**Module Organization:**
- Each module has a docstring at top: `"""This module contains..."""`
- Single responsibility per module: `file_service.py` only handles file operations
- Separate concerns: API routes in `api/`, business logic in `services/`, domain logic in `domain/`
- Infrastructure code in `infrastructure/` directory

## Pydantic Models

**Configuration:**
- Use `ConfigDict` for model configuration: `model_config = ConfigDict(...)`
- Enable validation and serialization attributes
- Example from `app/schemas.py`: `response_model = Response` for API endpoints

**Field Usage:**
- Use `Field` for documentation: `Field(..., description="Task identifier")`
- Validators with `@field_validator` for custom logic
- Class methods for factories: `from_domain()` to convert from domain objects

## Testing Markers

**Test Categories:** Marked with pytest markers for categorization
- `@pytest.mark.unit` - Fast tests with all dependencies mocked
- `@pytest.mark.integration` - Tests with real database or external services
- `@pytest.mark.e2e` - End-to-end tests through API
- `@pytest.mark.slow` - Slow tests (ML operations, large files)

---

*Convention analysis: 2026-01-27*
