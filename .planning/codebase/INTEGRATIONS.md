# External Integrations

**Analysis Date:** 2026-01-27

## APIs & External Services

**HuggingFace Hub:**
- HuggingFace Model Hub - ML model downloads and authentication
  - SDK/Client: whisperx (with PyAnnote models)
  - Auth: `HF_TOKEN` environment variable (required for diarization models from HuggingFace)
  - Used in: `app/infrastructure/ml/whisperx_diarization_service.py` (line 62 - `DiarizationPipeline(use_auth_token=self.hf_token)`)

**Webhook/Callback Destinations:**
- User-specified callback URLs for task completion notifications
  - HTTP Client: httpx 0.28.1
  - Auth: None (endpoint can require custom authentication)
  - Config: Timeout 10s (configurable via `CALLBACK_TIMEOUT`), max 3 retries with exponential backoff (configurable via `CALLBACK_MAX_RETRIES`)
  - Implemented in: `app/callbacks.py`
  - Validation: HEAD request validation before accepting callback URL

## Data Storage

**Databases:**
- SQLite (default) - Local file-based database for development/testing
  - Connection: `DB_URL=sqlite:///records.db` (configurable, default in `.env.example`)
  - Client: SQLAlchemy ORM
  - Location: `app/infrastructure/database/connection.py`, `app/infrastructure/database/models.py`

- PostgreSQL (optional) - Production database option
  - Connection: `DB_URL=postgresql://user:pass@localhost/dbname`
  - Client: SQLAlchemy ORM with psycopg2 driver

- MySQL (optional) - Alternative production database
  - Connection: `DB_URL=mysql://user:pass@localhost/dbname`
  - Client: SQLAlchemy ORM with appropriate MySQL driver

**File Storage:**
- Local filesystem only - Audio/video files stored locally
- Temporary files: System temp directory (NamedTemporaryFile)
- Cache directories (Docker): `/root/.cache` for model cache, `/tmp` for temporary files

**Caching:**
- Model cache: HuggingFace model cache (~/.cache/huggingface)
- PyTorch cache: ~/.cache/torch_models
- In-memory caching: Singleton pattern for ML model instances (WhisperX, diarization, alignment models)

## Authentication & Identity

**Auth Provider:**
- Custom Token (HuggingFace API token only)
  - Implementation: Direct token passing to HuggingFace via environment variable
  - Scope: Model downloads and PyAnnote diarization model access only
  - No application-level authentication mechanism (API is open access)

## Monitoring & Observability

**Error Tracking:**
- None detected - No external error tracking service integrated (Sentry, DataDog, etc.)

**Logs:**
- Local file system and stdout
- Framework: Python logging module with colorlog wrapper
- Format: Text or JSON (configurable via `LOG_FORMAT`)
- Level: Configurable via `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Implementation: `app/core/logging.py`

**Health Checks:**
- Built-in endpoints:
  - `/health` - Simple status check (returns `{"status": "ok"}`)
  - `/health/live` - Liveness check with timestamp (Kubernetes compatible)
  - `/health/ready` - Readiness check with database connectivity verification
- Docker: HEALTHCHECK configured (interval 30s, timeout 3s, 5s startup period, 3 retries)

## CI/CD & Deployment

**Hosting:**
- Docker container deployment (single container, currently single worker)
- Docker Compose for local orchestration with GPU support

**CI Pipeline:**
- Pre-commit hooks configured in `.pre-commit-config.yaml`
- Hooks include: ruff linting, mypy type checking, codespell
- No external CI service detected (GitHub Actions, GitLab CI, etc.)

**Deployment:**
- Gunicorn with Uvicorn workers (1 worker configured in Dockerfile)
- Entrypoint: `gunicorn --bind 0.0.0.0:8000 --workers 1 --timeout 0 --log-config gunicorn_logging.conf app.main:app -k uvicorn.workers.UvicornWorker`
- Port: 8000 (configurable via deployment)

## Environment Configuration

**Required env vars:**
- `HF_TOKEN` - HuggingFace API token (required for diarization model access)
- `WHISPER_MODEL` - Model size (tiny, base, small, medium, large, distil-*, etc.) - Default: tiny
- `DEVICE` - Computation device (cuda or cpu) - Auto-detected if available
- `COMPUTE_TYPE` - Precision mode (float16, int8) - Auto-corrected for CPU (must be int8)
- `DB_URL` - Database connection URL - Default: `sqlite:///records.db`
- `LOG_LEVEL` - Logging verbosity - Default: INFO
- `ENVIRONMENT` - Execution mode (development, testing, production) - Default: production

**Optional env vars:**
- `DEFAULT_LANG` - Default transcription language (ISO 639-1 code) - Default: en
- `DB_ECHO` - SQL query logging - Default: false
- `LOG_FORMAT` - Log output format (text or json) - Default: text
- `FILTER_WARNING` - Filter specific library warnings - Default: true
- `CALLBACK_TIMEOUT` - Webhook callback timeout in seconds - Default: 10
- `CALLBACK_MAX_RETRIES` - Callback retry attempts - Default: 3

**Secrets location:**
- `.env` file (local, not committed to git)
- Environment variables injected at runtime in containers

## Webhooks & Callbacks

**Incoming:**
- Not applicable - API is REST request-response only

**Outgoing:**
- Task completion webhooks to user-specified callback URLs
- Trigger: When task status changes to "completed" or "failed"
- Method: POST request with JSON payload containing task results
- Implementation: `app/callbacks.py` (validate_callback_url, post_task_callback functions)
- Payload serialization: Custom datetime serialization to ISO format
- Retry behavior: Exponential backoff (2^attempt seconds between retries, max 3 attempts)
- Error handling: Logged warnings, no exception raised after max retries

## Third-Party Model Services

**OpenAI Whisper Models:**
- Downloaded from HuggingFace Hub
- Models: tiny, tiny.en, base, base.en, small, small.en, medium, medium.en, large, large-v1, large-v2, large-v3, large-v3-turbo, distil-large-v2, distil-large-v3, distil-medium.en, distil-small.en
- Cache: Automatic download and cache to ~/.cache/huggingface

**PyAnnote Speaker Diarization:**
- Model: pyannote/speaker-diarization-3.0 or similar
- Source: HuggingFace Hub
- Auth: Requires `HF_TOKEN` for license acceptance
- Implementation: `app/infrastructure/ml/whisperx_diarization_service.py`

**WhisperX Alignment Model:**
- Phoneme alignment model for precise word-level timestamps
- Downloaded automatically via whisperx library
- No separate authentication required

---

*Integration audit: 2026-01-27*
