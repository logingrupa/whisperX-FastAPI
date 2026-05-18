"""Configuration for file upload handling."""

from pathlib import Path
from tempfile import gettempdir

from app.core.file_extensions import ALLOWED_EXTENSIONS

# Upload directory - use system temp by default
UPLOAD_DIR = Path(gettempdir()) / "whisperx_uploads"

# Maximum file size: 5GB per CONTEXT.md
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB in bytes

# Chunk size for streaming - 1MB is standard per RESEARCH.md
CHUNK_SIZE = 1024 * 1024  # 1MB

# Partial upload expiry - 10 minutes per CONTEXT.md
PARTIAL_UPLOAD_EXPIRY_SECONDS = 600

# Allowed extensions for streaming uploads — single source of truth lives in
# app.core.file_extensions. Exposed as a mutable set for callers that expect
# the historical type (no behavioural difference).
ALLOWED_UPLOAD_EXTENSIONS: set[str] = set(ALLOWED_EXTENSIONS)
