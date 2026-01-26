# Codebase Concerns

**Analysis Date:** 2026-01-27

## Tech Debt

**Legacy Configuration Class:**
- Issue: Deprecated `Config` class in `app/core/config.py` (line 158-175) exists alongside new `Settings` class. Old code still references `Config` directly instead of using `get_settings()`.
- Files: `app/core/config.py`, `app/services/whisperx_wrapper_service.py`, `app/services/file_service.py`, `app/core/logging.py`
- Impact: Inconsistent configuration access patterns, harder to maintain. New developers may add to `Config` class instead of `Settings`.
- Fix approach: Complete migration to `get_settings()` throughout codebase. Remove legacy `Config` class once all references updated.

**Subprocess Call Without Error Handling:**
- Issue: `subprocess.call()` in `app/audio.py` (line 25-40) ignores return code and doesn't validate ffmpeg success.
- Files: `app/audio.py:convert_video_to_audio()`
- Impact: Silent failures when ffmpeg is not installed or video conversion fails. Returns temp file path regardless of conversion status.
- Fix approach: Check `subprocess.call()` return code and raise exception on non-zero exit. Add validation that output file was created.

## Performance Bottlenecks

**GPU Memory Not Fully Managed:**
- Problem: While models are deleted and `torch.cuda.empty_cache()` is called, concurrent requests may cause memory fragmentation and OOM errors.
- Files: `app/services/whisperx_wrapper_service.py` (functions `transcribe_with_whisper`, `diarize`, `align_whisper_output`)
- Cause: No explicit memory pooling strategy. Background task CPU/GPU coordination lacks cleanup prioritization. ML models are large (base: ~140MB, medium: ~405MB, large: ~3GB).
- Improvement path: Implement model pre-loading/caching at startup rather than per-request. Add memory monitoring and queue management to limit concurrent processing. Consider model quantization for smaller footprint.

**Excessive Logging in Hot Paths:**
- Problem: GPU memory status logged at DEBUG level during transcription/alignment/diarization in every operation (lines 79, 112, 124, etc. in whisperx_wrapper_service.py).
- Files: `app/services/whisperx_wrapper_service.py:transcribe_with_whisper()`, `diarize()`, `align_whisper_output()`
- Cause: 6-8 GPU memory debug logs per operation with f-string calculations. In bulk processing, multiplies I/O overhead.
- Improvement path: Log GPU memory only on ERROR or at startup/shutdown. Use sampling strategy for DEBUG mode (e.g., every Nth request).

**No Connection Pooling Configuration:**
- Problem: Database connections created per-request without explicit pool sizing.
- Files: `app/infrastructure/database/connection.py` (SessionLocal usage)
- Cause: SQLAlchemy ORM default pool size (5 connections) may be insufficient for concurrent requests. No pool_recycle set.
- Improvement path: Configure pool_size and max_overflow in database engine setup. Add pool_recycle for long-running connections to prevent "connection lost" errors.

## Missing Error Handling

**Unhandled Exceptions in Background Tasks:**
- Problem: Background audio processing task in `app/services/whisperx_wrapper_service.py:process_audio_common()` catches only `RuntimeError`, `ValueError`, `KeyError`, `MemoryError` (lines 392-413). Many other exceptions (e.g., `AttributeError`, `TypeError`, `ImportError` from ML libraries) propagate unhandled.
- Files: `app/services/whisperx_wrapper_service.py:process_audio_common()` (lines 392-413)
- Impact: Unhandled exceptions fail silently in background tasks. Task status remains in "processing" forever. User never gets callback or completion signal.
- Safe modification: Wrap entire try block with broad `except Exception as e` clause. Log full traceback for investigation. Mark task as failed with error message.

**Missing Cleanup on Early Return:**
- Problem: Session cleanup only in `finally` block (line 415-446). If callback posting fails in finally block, session.close() may not execute.
- Files: `app/services/whisperx_wrapper_service.py:process_audio_common()` (finally block at line 415)
- Impact: Database session leak on exception during callback execution. Multiple nested try/finally blocks mask failure.
- Safe modification: Use context manager for session: `with SessionLocal() as session:` instead of manual close. Move callback posting outside finally or to separate task.

**Subprocess Call Return Code Never Checked:**
- Problem: `subprocess.call()` in `app/audio.py:convert_video_to_audio()` (line 25) doesn't check return code. Returns temp file path even if ffmpeg failed.
- Files: `app/audio.py:convert_video_to_audio()` (lines 14-41)
- Impact: Returns corrupt/incomplete audio file. Transcription will silently produce empty or garbled results. No error signal to user.
- Fix approach: Check return code and raise exception. Validate output file exists and has non-zero size.

**Missing Validation of URL Downloads:**
- Problem: `app/services/file_service.py:download_from_url()` validates extension but doesn't validate file size limits or corrupted downloads.
- Files: `app/services/file_service.py:download_from_url()` (lines 112-180)
- Impact: Users could upload unlimited-size files via URL. Incomplete downloads not detected. Could cause OOM or infinite loops during processing.
- Fix approach: Check Content-Length header before download. Validate downloaded file size. Add max_size parameter and enforce limits.

## Fragile Areas

**Audio Processing Pipeline Chain:**
- Files: `app/audio.py:process_audio_file()`, `app/services/audio_processing_service.py`
- Why fragile: Chain of implicit conversions and library calls. Video->audio conversion relies on ffmpeg system binary. Audio loading via whisperx library expects specific formats.
- Safe modification: Wrap each step with try/except. Validate intermediate files. Add detailed error messages about what failed.
- Test coverage: Only basic e2e tests in `tests/e2e/test_audio_processing_endpoints.py`. No unit tests for `convert_video_to_audio()` or audio loading edge cases.

**Database Session Management:**
- Files: `app/infrastructure/database/connection.py`, `app/services/whisperx_wrapper_service.py:process_audio_common()`
- Why fragile: SessionLocal() created manually in background task (line 296). No context manager. Session.close() in finally block but not guaranteed to execute if exception in exception handler.
- Safe modification: Use SQLAlchemy context manager or Dependency Injection container to manage session lifecycle.
- Test coverage: Integration tests use mock repositories. Real database session handling not tested under error conditions.

**Callback Retry Logic:**
- Files: `app/callbacks.py:post_task_callback()` (lines 93-155)
- Why fragile: Uses `time.sleep()` in async context (called from background task, not async function). Exponential backoff can take 7+ seconds (2^0 + 2^1 + 2^2). Blocks async event loop during retries.
- Safe modification: Use async sleep (`asyncio.sleep()`) or move to separate worker queue. Reduce max_retries or retry delay.
- Test coverage: Callbacks have e2e tests but retry logic not tested for blocking behavior.

**Task Status Transition State Machine:**
- Files: `app/domain/entities/task.py`, `app/api/task_api.py`, `app/services/whisperx_wrapper_service.py`
- Why fragile: No explicit state validation. Task status updated directly with string values. No validation that transitions are legal (e.g., can't go from completed to processing).
- Safe modification: Implement explicit state machine with enum validation before each status update.
- Test coverage: State transitions not explicitly tested. Integration tests only check happy path.

## Scaling Limits

**Single-Process Model Loading:**
- Current capacity: 1 large model (~3GB) in memory at a time. Requests queue indefinitely.
- Limit: With 8GB GPU, loading large model + processing audio + diarization leaves no headroom. Second concurrent request fails with OOM.
- Scaling path: Implement model preloading and caching at startup. Use model quantization. Deploy worker pool architecture (separate workers for transcription/diarization).

**SQLite Database for Production:**
- Current capacity: SQLite suitable for development. No concurrent write support. Locking becomes bottleneck.
- Limit: Multiple background tasks attempting to update task status simultaneously will queue writes, causing timeouts.
- Scaling path: Migrate to PostgreSQL for production. Add connection pooling. Implement optimistic locking for concurrent updates.

**No Request Queue Limits:**
- Current capacity: BackgroundTasks will queue unlimited requests. All tasks held in memory waiting for processing.
- Limit: With 50 concurrent uploads and 5-minute processing time, 250+ tasks in memory consuming heap space.
- Scaling path: Implement persistent task queue (Celery, RQ) with Redis backing. Add max queue size enforcement. Return 429 (Too Many Requests) when queue full.

**Single Event Loop Blocking:**
- Current capacity: FastAPI uses single async event loop. Callback retry logic uses `time.sleep()` blocking for 2-7 seconds.
- Limit: During callback retries, API becomes unresponsive for other requests.
- Scaling path: Make callback posting fully async. Use ASGI task queue. Move callbacks to separate worker.

## Test Coverage Gaps

**Audio Conversion Not Tested:**
- What's not tested: `app/audio.py:convert_video_to_audio()` function. No tests for ffmpeg failures, missing dependencies, or corrupted output.
- Files: `app/audio.py`
- Risk: Silent failures. Transcription produces empty results. No user feedback.
- Priority: High - This is called for all video uploads.

**Background Task Exception Handling:**
- What's not tested: Exception handling in `process_audio_common()`. Unhandled exceptions and partial failures in transcription/diarization/alignment steps.
- Files: `app/services/whisperx_wrapper_service.py:process_audio_common()` (lines 299-446)
- Risk: Background tasks fail silently. Database left in inconsistent state. Tasks never complete.
- Priority: High - Affects user experience and system reliability.

**File Download and Validation:**
- What's not tested: `app/services/file_service.py:download_from_url()` with corrupted files, timeouts, size limits, or invalid headers.
- Files: `app/services/file_service.py`
- Risk: OOM from huge files. Silent failures on incomplete downloads. Path traversal possible if extension validation fails.
- Priority: High - Security and stability impact.

**Database Session Cleanup:**
- What's not tested: Session cleanup under exception conditions. Connection pool exhaustion. Concurrent session creation.
- Files: `app/infrastructure/database/connection.py`, background task session handling
- Risk: Database connection leaks. Pool exhaustion causing hangs.
- Priority: Medium - Affects reliability under load.

**State Machine Transitions:**
- What's not tested: Invalid task status transitions (e.g., completed -> processing). Concurrent updates to same task status.
- Files: `app/domain/entities/task.py`, `app/api/task_api.py`
- Risk: Data corruption. Tasks in invalid states. Race conditions.
- Priority: Medium - Data integrity issue.

**Memory Management Under Load:**
- What's not tested: GPU memory behavior with concurrent requests. Memory cleanup after failed operations. Behavior when memory exhausted mid-transcription.
- Files: `app/services/whisperx_wrapper_service.py`
- Risk: OOM crashes. Incomplete cleanup. Process restart loops.
- Priority: High - Stability and reliability.

**Callback Retry Blocking:**
- What's not tested: Callback retry logic blocking async event loop. Performance impact of exponential backoff. Behavior when callback endpoint is slow.
- Files: `app/callbacks.py:post_task_callback()`
- Risk: API becomes unresponsive during retries. Event loop starvation.
- Priority: Medium - Performance impact.

## Security Considerations

**Temporary File Cleanup:**
- Risk: Uploaded files and downloaded files saved to temp directory but never explicitly deleted. `/tmp` or temp folder could fill up. Sensitive audio data persists on disk.
- Files: `app/services/file_service.py:save_upload()` (line 99), `download_from_url()` (line 162)
- Current mitigation: OS temp directory auto-cleanup (varies by OS). No explicit file deletion.
- Recommendations: Explicitly delete temp files after processing. Use context manager for temp files. Consider in-memory audio buffers for small files. Implement audio data encryption on disk.

**Subprocess Shell Injection Risk:**
- Risk: While ffmpeg call uses list args (safe from shell injection), ffmpeg command is hardcoded. No validation of audio file content before ffmpeg processing.
- Files: `app/audio.py:convert_video_to_audio()` (line 25-39)
- Current mitigation: File extension validated before calling convert_video_to_audio(). Ffmpeg called with fixed arguments.
- Recommendations: Add additional file format validation using magic bytes. Implement timeout for ffmpeg subprocess. Catch subprocess exceptions.

**HuggingFace Token in Env:**
- Risk: HF_TOKEN stored in environment variables. Could leak in logs or error messages.
- Files: Configuration in `app/core/config.py:WhisperSettings` (line 29-31). Used in `app/services/whisperx_wrapper_service.py:diarize()` (line 156)
- Current mitigation: Token used only for model downloads. Not logged explicitly.
- Recommendations: Validate token format before use. Add log filtering to redact token. Use secrets management service in production.

**Callback URL Validation Insufficient:**
- Risk: Callback URL validated with HEAD request, but SSRF possible. URL could point to internal services.
- Files: `app/callbacks.py:validate_callback_url()` (lines 15-49)
- Current mitigation: HEAD request made to URL to validate reachability.
- Recommendations: Validate URL against blocklist of internal IPs (127.0.0.1, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16). Implement URL scheme whitelist (https only in production).

**SQL Injection Risk in Old Code:**
- Risk: Old repository functions in `app/infrastructure/database/task_repository.py` use raw SQL string concatenation patterns (if any exist).
- Files: `app/infrastructure/database/task_repository.py`
- Current mitigation: SQLAlchemy ORM used throughout. No raw SQL observed.
- Recommendations: Remove all legacy raw SQL. Use parameterized queries exclusively.

**No Request Size Limits:**
- Risk: FastAPI default max upload size could allow DoS. No explicit file size limit enforced.
- Files: `app/api/audio_api.py` (file upload endpoints)
- Current mitigation: None observed.
- Recommendations: Add max file size validation. Set `max_size` in UploadFile. Return 413 (Payload Too Large) for oversized requests.

## Dependencies at Risk

**Numba 0.63.1:**
- Risk: Numba is a critical dependency for performance. Version pinned to 0.63.1. Older versions have known memory issues with complex audio processing.
- Impact: If production hits memory leak, requires upgrade. Incompatible with newer CUDA versions.
- Migration plan: Monitor Numba releases. Test with latest version in CI. Have upgrade path documented.

**PyTorch Version Constraints:**
- Risk: `torch<=2.8.0`, `torchaudio<=2.8.0`, `torchvision<=0.23.0` are upper-bound constrained. This prevents newer versions with bug fixes.
- Impact: Cannot adopt PyTorch bug fixes or performance improvements. CUDA 12.8 support may be missing.
- Migration plan: Test with latest stable PyTorch version. Remove upper bounds once testing completes. Use version ranges instead of hard caps.

**Setuptools CVE Workaround:**
- Risk: `setuptools>=78.1.1` explicitly added to fix CVE-2025-47273 (line 45 in pyproject.toml). This indicates recent security issue in tooling.
- Impact: Build process was vulnerable. If version constraint removed or ignored, vulnerability returns.
- Migration plan: Monitor setuptools releases. Keep constraint until vulnerability is well-patched upstream.

**WhisperX 3.7.4 Maintenance Status:**
- Risk: WhisperX is a third-party wrapper. Unclear maintenance status. Version pinned to 3.7.4.
- Impact: If WhisperX has bugs or incompatibilities with newer PyTorch, no fixes available.
- Migration plan: Monitor WhisperX releases. Consider dependency on openai-whisper directly. Have alternative ASR library identified.

## Known Bugs

**Video Conversion Silent Failure:**
- Symptoms: Uploading .mp4 file produces empty or garbled transcription. No error message.
- Files: `app/audio.py:convert_video_to_audio()` (line 25)
- Trigger: Upload video file with ffmpeg not installed or video codec not supported by ffmpeg.
- Workaround: Check server logs for ffmpeg errors. Pre-validate video codec. Install ffmpeg with all codec libraries.

**GPU Memory Not Freed After Task Fails:**
- Symptoms: After a failed transcription task (e.g., OOM), next task also fails with OOM even on small files. GPU memory remains high.
- Files: `app/services/whisperx_wrapper_service.py:process_audio_common()` (exception handling lines 392-413)
- Trigger: Transcription fails before reaching cleanup code. Exception thrown in `transcription_svc.transcribe()` (line 319).
- Workaround: Restart application to clear GPU memory. Monitor GPU memory with `nvidia-smi`.

**Task Status Never Updates on Callback Failure:**
- Symptoms: Task marked as completed but callback post fails. Task remains as completed in database but user never receives result.
- Files: `app/services/whisperx_wrapper_service.py:finally block` (lines 415-446)
- Trigger: Callback URL is reachable during validation but becomes unreachable during actual post (network outage, target server crashes).
- Workaround: Implement polling mechanism for task status. Don't rely solely on callbacks.

---

*Concerns audit: 2026-01-27*
