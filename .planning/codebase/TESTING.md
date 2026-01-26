# Testing Patterns

**Analysis Date:** 2026-01-27

## Test Framework

**Runner:**
- pytest v9.0.2
- Config file: `pyproject.toml` under `[tool.pytest.ini_options]`
- Test discovery: Files matching `test_*.py`, classes matching `Test*`, functions matching `test_*`
- Strict markers required: `--strict-markers --strict-config` enforced

**Assertion Library:**
- Standard pytest assertions: `assert response.status_code == 200`
- `pytest.approx()` for floating-point comparisons: `assert retrieved.duration == pytest.approx(10.5)`
- `pytest.raises()` for exception testing: `with pytest.raises(ValueError, match="Task not found"):`

**Run Commands:**
```bash
pytest tests/                     # Run all tests
pytest tests/ -v                 # Verbose output
pytest tests/ -k "health"        # Run tests matching pattern
pytest tests/ --markers          # List available markers
pytest tests/ -m "unit"          # Run only unit tests
pytest tests/ --cov=app          # Generate coverage report
```

## Test File Organization

**Location:**
- Co-located with test discovery in `tests/` directory at project root
- Organized by test type: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- Fixtures in `tests/fixtures/` directory
- Mocks in `tests/mocks/` directory
- Factories in `tests/factories/` directory
- Test data files in `tests/test_files/`

**Naming:**
- Test modules: `test_*.py` (e.g., `test_health_endpoints.py`)
- Test classes: `Test*` (e.g., `TestTaskLifecycle`)
- Test functions: `test_*` (e.g., `test_create_and_retrieve_task`)
- Fixtures: Function name with `@pytest.fixture` decorator

**Structure:**
```
tests/
├── conftest.py              # Session-scoped fixtures and setup
├── fixtures/
│   ├── __init__.py
│   ├── database.py         # Database session fixture
│   └── test_container.py   # Dependency injection container
├── factories/
│   ├── __init__.py
│   └── task_factory.py     # Factory-boy factories
├── mocks/
│   ├── __init__.py
│   ├── mock_transcription_service.py
│   └── ...other mocks
├── e2e/
│   ├── __init__.py
│   ├── test_health_endpoints.py
│   └── test_audio_processing_endpoints.py
├── integration/
│   ├── __init__.py
│   └── test_task_lifecycle.py
└── test_files/
    └── audio_en.mp3
```

## Test Structure

**Suite Organization:**
```python
# From tests/e2e/test_health_endpoints.py
@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create and return test client."""
    from app import main
    return TestClient(main.app, follow_redirects=False)

@pytest.mark.e2e
def test_health_check(client: TestClient) -> None:
    """Test the basic health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
```

**Integration Test Class Pattern:**
```python
# From tests/integration/test_task_lifecycle.py
@pytest.mark.integration
class TestTaskLifecycle:
    """Integration tests for complete task lifecycle with real database."""

    def test_create_and_retrieve_task(self, db_session: Session) -> None:
        """Test creating a task and retrieving it from database."""
        repository = SQLAlchemyTaskRepository(db_session)
        task = TaskFactory(uuid="integration-test-123", status="pending")
        task_id = repository.add(task)

        retrieved = repository.get_by_id(task_id)
        assert retrieved is not None
        assert retrieved.uuid == "integration-test-123"
```

**Patterns:**
- **Setup**: Create test data using factories or fixtures before assertions
- **Execution**: Call the function/endpoint being tested
- **Assertion**: Verify results with explicit assertions
- **Teardown**: Fixtures handle cleanup automatically (no manual cleanup needed)

## Mocking

**Framework:** factory-boy for test data generation, custom mock classes for services

**Patterns:**
```python
# From tests/mocks/mock_transcription_service.py
class MockTranscriptionService:
    """Mock transcription service for testing."""

    def __init__(
        self, mock_result: dict[str, Any] | None = None, should_fail: bool = False
    ) -> None:
        self.mock_result = mock_result or self._default_result()
        self.should_fail = should_fail
        self.transcribe_called = False
        self.transcribe_call_count = 0

    def transcribe(
        self,
        audio: np.ndarray[Any, np.dtype[np.float32]],
        task: str,
        # ...parameters...
    ) -> dict[str, Any]:
        """Return mock transcription result immediately."""
        self.transcribe_called = True
        self.transcribe_call_count += 1

        if self.should_fail:
            raise RuntimeError("Mock transcription failed")

        return self.mock_result
```

**Dependency Injection for Testing:**
```python
# From tests/fixtures/test_container.py
class TestContainer(Container):
    """Test container that overrides production services with mocks."""

    # Override ML services with fast mocks
    transcription_service = providers.Singleton(MockTranscriptionService)
    diarization_service = providers.Singleton(
        MockDiarizationService,
        hf_token="mock_token",
    )
    alignment_service = providers.Singleton(MockAlignmentService)

    # Override database with in-memory SQLite
    db_engine = providers.Singleton(
        create_engine,
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
```

**What to Mock:**
- External ML services (transcription, diarization, alignment)
- File downloads and uploads (FileService)
- Database connections (use in-memory SQLite instead)
- Network calls (use monkeypatch for httpx)

**What NOT to Mock:**
- Domain logic (entities, value objects)
- Business rule validation
- Repository pattern (use real database with test data)
- FastAPI TestClient (provides real HTTP simulation)

## Fixtures and Factories

**Test Data Generation:**
```python
# From tests/factories/task_factory.py
class TaskFactory(factory.Factory):
    """Factory for creating test Task entities."""

    class Meta:
        model = Task

    uuid = factory.Sequence(lambda n: f"task-{n}")
    status = "pending"
    task_type = "transcription"
    result = None
    file_name = Faker("file_name", extension="mp3")
    audio_duration = Faker("pyfloat", min_value=1.0, max_value=600.0)
    language = "en"
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    def processing(cls, **kwargs: Any) -> Task:
        """Create a task in processing status with start time."""
        return cls(status="processing", start_time=datetime.now(timezone.utc), **kwargs)

    @classmethod
    def completed(cls, **kwargs: Any) -> Task:
        """Create a completed task with result and timing."""
        return cls(
            status="completed",
            result={"segments": [{"text": "Test transcription"}]},
            duration=10.5,
            **kwargs,
        )
```

**Usage in Tests:**
```python
# Simple creation with defaults
task = TaskFactory()

# Customized creation
task = TaskFactory(uuid="test-123", status="processing")

# Factory methods for specific states
task = TaskFactory.completed(uuid="completed-task")
task = TaskFactory.failed(uuid="failed-task")
```

**Location:**
- `tests/factories/task_factory.py` - Single factory per domain entity
- `tests/factories/__init__.py` - Exports all factories for convenient imports
- One factory class per entity type

## Pytest Fixtures

**Session-scoped Fixtures (in `conftest.py`):**
```python
@pytest.fixture(scope="session", autouse=True)
def setup_test_db(tmp_path_factory: pytest.TempPathFactory) -> Generator[None, None, None]:
    """Session-scoped fixture to set up test database and environment variables."""
    test_db_file = tmp_path_factory.mktemp("db_dir") / "test.db"
    os.environ["DB_URL"] = f"sqlite:///{test_db_file}"
    os.environ["DEVICE"] = "cpu"
    os.environ["COMPUTE_TYPE"] = "int8"
    os.environ["WHISPER_MODEL"] = "tiny"

    # Create tables
    from app.infrastructure.database import Base, engine
    Base.metadata.create_all(bind=engine)

    yield
    # Cleanup handled by tmp_path_factory
```

**Function-scoped Fixtures:**
```python
@pytest.fixture(scope="function")
def test_container() -> Generator[TestContainer, None, None]:
    """Provide a test container with mock implementations for testing."""
    container = TestContainer()
    yield container
    # Cleanup happens automatically
```

**Module-scoped Fixtures (in test files):**
```python
@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create and return test client."""
    from app import main
    return TestClient(main.app, follow_redirects=False)
```

## Coverage

**Configuration (pyproject.toml):**
```toml
[tool.coverage.run]
source = ["app"]
omit = [
    "tests/*",
    "/tmp/*",
    "venv/*",
    "*/virtualenv/*",
    "*/site-packages/*"
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "pass",
    "raise ImportError"
]
```

**View Coverage:**
```bash
pytest tests/ --cov=app --cov-report=html     # Generate HTML report
pytest tests/ --cov=app --cov-report=term-missing  # Terminal with missing lines
```

**Coverage Report:**
- HTML report in `htmlcov/index.html`
- Terminal shows percentage per module
- Excludes test files, repr methods, abstract methods automatically

## Test Types

**Unit Tests:**
- Scope: Single function/method in isolation
- Dependencies: All mocked (no real I/O, no real network)
- Location: `tests/unit/`
- Marker: `@pytest.mark.unit`
- Speed: <100ms per test
- Example: Test `validate_file_extension()` with various inputs

**Integration Tests:**
- Scope: Multiple components working together
- Dependencies: Real database (SQLite in-memory), real repositories
- Location: `tests/integration/`
- Marker: `@pytest.mark.integration`
- Speed: 100ms-1s per test
- Example: `TestTaskLifecycle` - tests full repository workflow with real DB

**E2E Tests:**
- Scope: Full API endpoints through HTTP
- Dependencies: Real app instance, real database, mocked ML services
- Location: `tests/e2e/`
- Marker: `@pytest.mark.e2e`
- Speed: 1-10s per test
- Tools: FastAPI TestClient for HTTP simulation
- Example: `test_health_endpoints.py` - tests endpoints like GET /health

**Slow Tests:**
- ML operations, file processing, network calls
- Marker: `@pytest.mark.slow`
- Run separately in CI/CD

## Common Patterns

**Async Testing:**
```python
# FastAPI TestClient handles async automatically
# No need for @pytest.mark.asyncio or event_loop fixture
def test_async_endpoint(client: TestClient) -> None:
    response = client.post("/speech-to-text", files={"file": ("test.mp3", b"data")})
    assert response.status_code == 200
```

**Error Testing:**
```python
# From tests/integration/test_task_lifecycle.py
def test_update_nonexistent_task_raises_error(self, db_session: Session) -> None:
    """Test updating non-existent task raises ValueError."""
    repository = SQLAlchemyTaskRepository(db_session)

    with pytest.raises(ValueError, match="Task not found"):
        repository.update("non-existent-uuid", {"status": "completed"})
```

**Parametrized Tests:**
```python
@pytest.mark.parametrize("status,expected", [
    ("processing", False),
    ("completed", True),
])
def test_is_completed(status: str, expected: bool) -> None:
    task = TaskFactory(status=status)
    assert task.is_completed() == expected
```

**Monkeypatch for Isolation:**
```python
# From tests/e2e/test_health_endpoints.py
def test_readiness_check_with_db_failure(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    """Test readiness check when database connection fails."""
    from app.infrastructure.database import engine

    def mock_connect(*args: Any, **kwargs: Any) -> Any:
        class MockConnection:
            def __enter__(self) -> "MockConnection":
                raise TimeoutError("Database connection failed")

            def __exit__(self, *args: Any) -> None:
                pass

        return MockConnection()

    original_connect = engine.connect
    monkeypatch.setattr(engine, "connect", mock_connect)

    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
    finally:
        monkeypatch.setattr(engine, "connect", original_connect)
```

**Database Session Fixture:**
```python
# From tests/fixtures/database.py
@pytest.fixture
def db_session(test_db_engine) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    connection = test_db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

---

*Testing analysis: 2026-01-27*
