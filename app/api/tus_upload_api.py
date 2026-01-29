"""TUS protocol upload router for chunked file uploads.

Provides a TUS-compliant upload endpoint at /uploads/files/ using tuspyserver.
Supports resumable uploads up to 5GB with automatic expiry cleanup.
"""

from pathlib import Path

from fastapi import APIRouter
from tuspyserver import create_tus_router

from app.core.upload_config import UPLOAD_DIR

# TUS-specific storage directory (separate from streaming uploads)
TUS_UPLOAD_DIR: Path = UPLOAD_DIR / "tus"

# Create TUS protocol router via tuspyserver
tus_router: APIRouter = create_tus_router(
    prefix="files",
    files_dir=str(TUS_UPLOAD_DIR),
    max_size=5 * 1024 * 1024 * 1024,  # 5GB max (matches MAX_FILE_SIZE)
    days_to_keep=1,
    upload_complete_dep=None,
)

# Wrapper router with /uploads prefix for mounting in main app
tus_upload_router: APIRouter = APIRouter(
    prefix="/uploads",
    tags=["TUS Upload"],
)
tus_upload_router.include_router(tus_router)
