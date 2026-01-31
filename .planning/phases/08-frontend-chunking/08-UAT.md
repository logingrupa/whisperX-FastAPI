---
status: diagnosed
phase: 08-frontend-chunking
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md]
started: 2026-01-31T15:50:00Z
updated: 2026-01-31T16:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Small File Uses Direct Upload
expected: Drop a file under 80MB. It uploads via the existing direct path (no TUS). Progress bar shows upload percentage. Transcription begins after upload completes.
result: pass

### 2. Large File Routes to TUS Upload
expected: Drop a file >= 80MB. It should automatically route to TUS chunked upload. Upload begins without error. You should NOT see a 413 or timeout error.
result: issue
reported: "PATCH to TUS endpoint returns 422 Unprocessable Content after upload completes. tus-js-client shows error in console."
severity: blocker

### 3. TUS Upload Progress Display
expected: During a large file (>= 80MB) TUS upload, the progress bar shows upload percentage advancing smoothly (not jumping erratically).
result: pass

### 4. TUS Upload Completes and Triggers Transcription
expected: After a large file TUS upload finishes, transcription starts automatically. You see transcription progress via WebSocket (processing stages).
result: issue
reported: "TUS upload completes (all PATCH 204s) but transcription fails with UnsupportedFileExtensionError — assembled file has no extension (stored as hash ID only). Backend returns 422, tus-js-client shows error."
severity: blocker

### 5. Backend Startup Clean
expected: Backend starts without errors in the log. No crashes or tracebacks on startup.
result: issue
reported: "ERROR during TUS upload cleanup: gc_files fails to parse expires date 'Fri, 30 Jan 2026 18:16:01 GMT' — ValueError: Invalid isoformat string. Cleanup scheduler runs but fails on existing stale uploads."
severity: major

## Summary

total: 5
passed: 2
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Large file TUS upload completes without 422 error"
  status: failed
  reason: "User reported: PATCH to TUS endpoint returns 422 Unprocessable Content after upload completes. tus-js-client shows error in console."
  severity: blocker
  test: 2
  root_cause: "Tests 2 and 4 share the same root cause. The on_complete hook in upload_session_service.py passes the raw TUS file path (hash ID with no extension) to process_audio_file(). check_file_extension() rejects the empty extension, raises UnsupportedFileExtensionError (a ValidationError subclass), which FastAPI's exception handler returns as HTTP 422 to tus-js-client."
  artifacts:
    - path: "app/services/upload_session_service.py"
      issue: "Passes extensionless TUS file path to process_audio_file without renaming"
    - path: "app/files.py"
      issue: "check_file_extension correctly rejects empty extension — working as designed"
  missing:
    - "Rename TUS file with original extension (from metadata) before calling process_audio_file"
  debug_session: ".planning/debug/tus-422-no-extension.md"

- truth: "TUS upload triggers transcription automatically after completion"
  status: failed
  reason: "User reported: TUS upload completes (all PATCH 204s) but transcription fails with UnsupportedFileExtensionError — assembled file has no extension (stored as hash ID only). Backend returns 422."
  severity: blocker
  test: 4
  root_cause: "Same root cause as Test 2. TUS stores files by hash ID without extension. upload_session_service.py already extracts filename and extension from metadata but doesn't rename the file before transcription."
  artifacts:
    - path: "app/services/upload_session_service.py"
      issue: "Lines 76-77 extract filename/extension from metadata but never use them to rename the file before line 83 process_audio_file call"
  missing:
    - "Add 3 lines between magic bytes check and process_audio_file: rename file with original extension from metadata"
  debug_session: ".planning/debug/tus-422-no-extension.md"

- truth: "Backend starts without errors in the log"
  status: failed
  reason: "User reported: gc_files fails to parse expires date 'Fri, 30 Jan 2026 18:16:01 GMT' — ValueError: Invalid isoformat string"
  severity: major
  test: 5
  root_cause: "tuspyserver library bug: creation.py writes expires dates in RFC 7231 format (formatdate() from email.utils) but file.py line 127 reads them with datetime.fromisoformat() which only accepts ISO 8601. The correct parser (parsedate_to_datetime) is already used elsewhere in the library (core.py _check_upload_expired)."
  artifacts:
    - path: ".venv/Lib/site-packages/tuspyserver/file.py"
      issue: "Line 127 uses fromisoformat() but dates are RFC 7231 format"
    - path: ".venv/Lib/site-packages/tuspyserver/routes/creation.py"
      issue: "Line 228 writes RFC 7231 dates via formatdate()"
  missing:
    - "Patch tuspyserver/file.py line 127: replace fromisoformat() with parsedate_to_datetime() (same pattern as existing fcntl→msvcrt patch)"
  debug_session: ".planning/debug/gc-files-date-parse.md"
