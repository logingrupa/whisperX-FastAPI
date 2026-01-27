"""Custom streaming target for large file uploads."""

from pathlib import Path
from typing import Optional

from streaming_form_data.targets import BaseTarget
from streaming_form_data.validators import MaxSizeValidator

from app.core.logging import logger
from app.core.upload_config import MAX_FILE_SIZE


class StreamingFileTarget(BaseTarget):
    """
    Custom target that streams uploaded file directly to disk.

    Uses streaming-form-data's BaseTarget interface to receive chunks
    as they arrive from the multipart parser, writing directly to disk
    without buffering the entire file in memory.
    """

    def __init__(self, filepath: Path, max_size: int = MAX_FILE_SIZE) -> None:
        """
        Initialize the streaming file target.

        Args:
            filepath: Path where the file will be written
            max_size: Maximum allowed file size in bytes (default: 5GB)
        """
        super().__init__(validator=MaxSizeValidator(max_size))
        self.filepath = filepath
        self._file: Optional[object] = None
        self._bytes_written = 0

    def on_start(self) -> None:
        """Called when file upload starts. Opens the file handle."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.filepath, "wb")
        self._bytes_written = 0
        logger.debug("Started streaming upload to: %s", self.filepath)

    def on_data_received(self, chunk: bytes) -> None:
        """
        Called for each chunk received.

        Args:
            chunk: Bytes received from the upload stream
        """
        if self._file is not None:
            self._file.write(chunk)  # type: ignore[union-attr]
            self._bytes_written += len(chunk)

    def on_finish(self) -> None:
        """Called when upload completes. Closes the file handle."""
        if self._file is not None:
            self._file.close()  # type: ignore[union-attr]
            self._file = None
        logger.info(
            "Completed streaming upload: %s (%d bytes)",
            self.filepath,
            self._bytes_written,
        )

    @property
    def bytes_written(self) -> int:
        """Return total bytes written to file."""
        return self._bytes_written
