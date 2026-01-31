---
status: resolved
trigger: "TUS PATCH returns 422 after upload completes; TUS assembled file has no extension"
created: 2026-01-31T00:00:00Z
updated: 2026-01-31T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - single root cause for both issues
test: full code trace completed
expecting: n/a
next_action: implement fix

## Symptoms

expected: TUS upload completes, transcription starts, client receives 204
actual: Final PATCH returns 422; backend logs UnsupportedFileExtensionError for extensionless file
errors:
  - "UnsupportedFileExtensionError: File '...\tus\5bc8507537dd483ab852a4955ab4e5a3' has unsupported extension ''"
  - tus-js-client shows error in browser console after final PATCH
reproduction: Upload any file via TUS chunked upload; last chunk triggers the error
started: Since TUS integration was added

## Eliminated

(none - root cause found on first hypothesis)

## Evidence

- timestamp: 2026-01-31T00:01:00Z
  checked: tuspyserver/file.py line 74 - TusUploadFile.path property
  found: Files stored as `{files_dir}/{uid}` with NO extension. uid is uuid4().hex (32 hex chars, no dots)
  implication: TUS assembled files will never have a file extension on disk

- timestamp: 2026-01-31T00:02:00Z
  checked: tuspyserver/routes/core.py lines 276-282 - core_patch_route completion hook
  found: When upload completes (size == offset), calls `on_complete(file_path, file.info.metadata)` where file_path = `os.path.join(files_dir, uuid)` (extensionless)
  implication: The hook receives the raw extensionless path, but metadata dict contains the original filename

- timestamp: 2026-01-31T00:03:00Z
  checked: app/services/upload_session_service.py line 83
  found: Calls `process_audio_file(file_path)` with the raw TUS path (no extension)
  implication: process_audio_file receives a path like `.../tus/5bc8507537dd483ab852a4955ab4e5a3`

- timestamp: 2026-01-31T00:04:00Z
  checked: app/audio.py line 53 -> app/files.py line 31
  found: `check_file_extension` calls `os.path.splitext(filename)[1].lower()` on the TUS path, returns empty string `""`
  implication: Empty string is not in ALLOWED_EXTENSIONS -> raises UnsupportedFileExtensionError

- timestamp: 2026-01-31T00:05:00Z
  checked: Exception hierarchy and handler registration
  found: UnsupportedFileExtensionError -> ValidationError -> DomainError -> ApplicationError. FastAPI has `app.add_exception_handler(ValidationError, validation_error_handler)` which returns HTTP 422.
  implication: The exception propagates from the on_complete hook back through the PATCH handler, FastAPI catches it and returns 422 to the client

- timestamp: 2026-01-31T00:06:00Z
  checked: upload_session_service.py lines 76-78 (magic bytes validation)
  found: Service ALREADY extracts extension from metadata: `filename = metadata.get("filename", ...)` then `extension = Path(filename).suffix`. But this is only used for magic bytes validation, NOT passed to process_audio_file.
  implication: The fix is already half-implemented - the service knows the original filename but doesn't use it when calling process_audio_file

## Resolution

root_cause: |
  SINGLE ROOT CAUSE for both issues. The TUS completion hook in `upload_session_service.py`
  calls `process_audio_file(file_path)` with the raw TUS storage path, which is a bare hex
  hash with no file extension (e.g., `tus/5bc8507537dd483ab852a4955ab4e5a3`).

  `process_audio_file` -> `check_file_extension` -> `validate_extension` extracts the extension
  via `os.path.splitext()`, gets empty string `""`, which is not in ALLOWED_EXTENSIONS, and
  raises `UnsupportedFileExtensionError`.

  This exception inherits from `ValidationError`, which has a registered FastAPI exception
  handler that returns HTTP 422. Since the exception is raised inside the TUS PATCH handler's
  `on_complete` callback (awaited at core.py line 282), FastAPI catches it and returns 422
  to the tus-js-client.

  **Issue 1 (422) is a DIRECT CONSEQUENCE of Issue 2 (no extension).** They are the same bug.

  The irony: `upload_session_service.py` already extracts the original filename and extension
  from TUS metadata (line 76-77) for magic bytes validation, but never uses it to rename/
  resolve the file before passing it to `process_audio_file`.

fix_direction: |
  The assembled TUS file should be renamed to include its original extension BEFORE calling
  `process_audio_file`. This is the correct approach because:

  1. `process_audio_file` uses the extension to decide whether to convert video->audio
  2. The original filename is already available in metadata
  3. Renaming is a simple `os.rename()` or `Path.rename()` in upload_session_service.py
  4. This keeps process_audio_file's contract unchanged (it expects files with extensions)

  Specifically, in `upload_session_service.py`, between the magic bytes validation (line 78)
  and the `process_audio_file` call (line 83), add:

  ```python
  # Rename TUS file to include original extension so process_audio_file can identify format
  original_path = Path(file_path)
  extended_path = original_path.with_suffix(extension)
  original_path.rename(extended_path)
  file_path = str(extended_path)
  ```

  Alternative (NOT recommended): Modify `process_audio_file` to accept an optional extension
  parameter. This would require changing the function signature and all callers, and is more
  invasive for no benefit.

verification: pending
files_changed: []
