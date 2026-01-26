# Technology Stack

**Analysis Date:** 2026-01-27

## Languages

**Primary:**
- Python 3.10+ (supports 3.10, 3.11) - All application code, ML pipeline

## Runtime

**Environment:**
- Python 3.11 (specified in Dockerfile and project config)
- UV package manager (version latest from ghcr.io/astral-sh/uv)

**Package Manager:**
- UV (Rust-based Python package manager)
- Lockfile: `uv.lock` (present, pinned dependencies)

## Frameworks

**Core:**
- FastAPI 0.128.0 - REST API framework
- Uvicorn 0.40.0 - ASGI server
- Gunicorn 23.0.0 - WSGI HTTP server for production

**Testing:**
- pytest 9.0.2 - Testing framework
- pytest-cov 7.0.0 - Coverage reporting

**Build/Dev:**
- setuptools >= 78.1.1 - Package building
- pre-commit 4.5.1 - Git hooks framework
- ruff 0.14.11 - Python linter/formatter
- mypy 1.19.1 - Static type checking

## Key Dependencies

**Critical:**
- whisperx 3.7.4 - Speech-to-text, alignment, and diarization models
- torch <= 2.8.0 - PyTorch ML framework (CUDA 12.8 on Linux, CPU variants for Windows/macOS)
- torchaudio <= 2.8.0 - Audio processing for ML
- torchvision <= 0.23.0 - Computer vision utilities
- sqlalchemy - ORM and database toolkit
- pydantic >= 2.0 - Data validation and settings management
- pydantic-settings >= 2.0.0 - Settings management with environment variable support

**Infrastructure:**
- httpx 0.28.1 - Async HTTP client for webhook callbacks
- python-dotenv 1.2.1 - Environment variable loading
- python-multipart 0.0.21 - Multipart form data parsing
- dependency-injector >= 4.41.0 - Dependency injection container
- colorlog 6.10.1 - Colored logging output
- tqdm 4.67.1 - Progress bar library
- numba 0.63.1 - JIT compilation for numerical code
- pandas - Data manipulation (used by diarization)
- numpy - Numerical computing
- ctranslate2 4.6.0 - Fast inference engine (installed in Docker)

**Development Only:**
- factory-boy 3.3.3 - Test fixture factories
- codespell 2.4.1 - Spell checker
- pandas-stubs >= 2.1.0 - Type hints for pandas
- types-requests >= 2.31.0 - Type hints
- types-PyYAML >= 6.0.12 - Type hints for YAML

## Configuration

**Environment:**
- Configuration via environment variables using Pydantic Settings
- Nested settings with `__` delimiter (e.g., `database__DB_URL`)
- Settings file: `.env` (loads via python-dotenv)
- Multiple environment contexts: development, testing, production

**Build:**
- `pyproject.toml` - Project metadata and dependencies
- `dockerfile` - Docker image with NVIDIA CUDA 13.0.1 base
- `docker-compose.yml` - Multi-container orchestration with GPU support
- `uvicorn` configuration - ASGI server settings

## Platform Requirements

**Development:**
- Python 3.10 or 3.11
- FFmpeg (for audio processing)
- CUDA Toolkit 12.6+ (optional, for GPU acceleration)

**Production:**
- Docker with NVIDIA GPU support (docker-compose configured with `nvidia/cuda:13.0.1` base image)
- CUDA 13.0.1 runtime
- GPU: NVIDIA GPU with CUDA capability (optional but recommended)
- Alternative: CPU-only mode with reduced performance
- Database: SQLite (default), PostgreSQL, or MySQL compatible

**Dependencies in Docker:**
- `libcudnn9-cuda-12=9.8.0.87-1` - NVIDIA cuDNN library
- `libatomic1` - Atomic operations library
- `curl` - HTTP client
- FFmpeg 7:4.4.2 - Audio/video processing

---

*Stack analysis: 2026-01-27*
