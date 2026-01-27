"""Configuration for file upload handling."""

from pathlib import Path
from tempfile import gettempdir

# Upload directory - use system temp by default
UPLOAD_DIR = Path(gettempdir()) / "whisperx_uploads"

# Maximum file size: 5GB per CONTEXT.md
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB in bytes

# Chunk size for streaming - 1MB is standard per RESEARCH.md
CHUNK_SIZE = 1024 * 1024  # 1MB

# Partial upload expiry - 10 minutes per CONTEXT.md
PARTIAL_UPLOAD_EXPIRY_SECONDS = 600

# Allowed extensions for streaming uploads (must match Config.ALLOWED_EXTENSIONS)
# Using explicit set here to avoid circular imports with Config
ALLOWED_UPLOAD_EXTENSIONS = {
    ".mp3", ".wav", ".awb", ".aac", ".ogg", ".oga", ".m4a", ".wma", ".amr",  # audio
    ".mp4", ".mov", ".avi", ".wmv", ".mkv",  # video
    ".flac", ".webm",  # additional from CONTEXT.md
}
