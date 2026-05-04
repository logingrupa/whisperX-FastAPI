---
slug: speech-to-text-500-winerror2
status: resolved
trigger: "User registered fine via frontend; then attempted to upload audio + transcribe via POST /speech-to-text?language=en&model=large-v3 and got 500 INTERNAL_ERROR. Backend log shows: WinError 2 (file not found) raised from subprocess.run inside whisperx/audio.py:61, called via load_audio() from app/audio.py:56 -> app/api/audio_api.py:104 (process_audio_file(temp_file)). Temp file was successfully written first (tmpif18ig6b.wav). Correlation id: 22056bc2-b665-42e8-a6e9-6f8d62bd8041. Stack frames bottom-up: _winapi.CreateProcess -> subprocess.Popen._execute_child -> whisperx.audio.load_audio (subprocess.run cmd) -> app.audio.process_audio_file -> audio_api.speech_to_text. Auth + cookies + CSRF all OK (request reached endpoint). Filename has spaces: '2025-03-22 Greetings.wav'."
created: 2026-05-04T21:54:03Z
updated: 2026-05-05T00:00:00Z
goal: find_and_fix
---

# Debug: speech-to-text 500 WinError 2 on upload

## Symptoms

- **Expected:** Audio file uploaded via POST /speech-to-text returns transcription (200 OK).
- **Actual:** 500 INTERNAL_ERROR returned to client, ~80 ms after upload reaches endpoint.
- **Error message (client):**
  ```json
  {
    "error": {
      "message": "An unexpected error occurred. Please contact support if the problem persists.",
      "code": "INTERNAL_ERROR",
      "correlation_id": "22056bc2-b665-42e8-a6e9-6f8d62bd8041"
    }
  }
  ```
- **Error message (server):** `[WinError 2] The system cannot find the file specified` raised from `subprocess.run` inside `whisperx/audio.py:61` (third-party whisperx package). Logged by `app.api.exception_handlers` as `Unexpected error`.
- **Timeline:** First time the user has tried to use transcribe after registering. No "ever worked" data point. Auth feature was just shipped; this may be the first end-to-end upload after the auth/DI refactor (phase 19).
- **Reproduction:** Sign in (fresh register), navigate to upload UI at `http://localhost:5173/ui/`, choose `2025-03-22 Greetings.wav`, submit. Frontend POST goes to `http://localhost:5173/speech-to-text?language=en&model=large-v3` (Vite dev proxy → backend). Server saves temp file (logged), then crashes during `process_audio_file(temp_file)`.

## Key trace evidence (from server log)

```
2026-05-05 00:49:34,323 - whisperX - INFO - Received file upload request: 2025-03-22 Greetings.wav
2026-05-05 00:49:34,357 - whisperX - INFO - 2025-03-22 Greetings.wav saved as temporary file: C:\Users\rolan\AppData\Local\Temp\tmpif18ig6b.wav
2026-05-05 00:49:34,403 - app.api.exception_handlers - ERROR - Unexpected error: [WinError 2] The system cannot find the file specified
  ...
  File "C:\laragon\www\whisperx\app\api\audio_api.py", line 104, in speech_to_text
    audio = process_audio_file(temp_file)
  File "C:\laragon\www\whisperx\app\audio.py", line 56, in process_audio_file
    return load_audio(audio_file)
  File "C:\laragon\www\whisperx\.venv\Lib\site-packages\whisperx\audio.py", line 61, in load_audio
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
  File "C:\laragon\bin\python\python-3.13\Lib\subprocess.py", line 1548, in _execute_child
    hp, ht, pid, tid = _winapi.CreateProcess(executable, args, ...)
```

## Environment

- OS: Windows 11 Pro (10.0.26200)
- Python: 3.13 (C:\laragon\bin\python\python-3.13)
- Backend: FastAPI, uvicorn, ENV=production
- Temp file IS written successfully (size unknown from log)
- whisperx package version: bundled in .venv

## Initial hypothesis ranking

1. **ffmpeg missing from PATH (high probability).** WhisperX's `load_audio` shells out to `ffmpeg` via `subprocess.run(cmd, ...)`. `WinError 2` from `_winapi.CreateProcess` after a successful temp-file write almost always means the *executable* (not the input file) cannot be found. The input file path was just logged and exists.
2. ffmpeg installed but not on the uvicorn process's PATH (e.g., installed in a user-only location, uvicorn started from a shell that doesn't inherit it).
3. Less likely: temp file path race or permission issue.

## Current Focus

- hypothesis: ffmpeg executable not found on PATH for the uvicorn process — `subprocess.run(["ffmpeg", ...])` fails with WinError 2 inside whisperx/audio.py:61.
- test: Inspect `whisperx/audio.py` line 61 area to confirm the cmd[0] is `ffmpeg`. Then run `where ffmpeg` (from a comparable shell) and `python -c "import shutil; print(shutil.which('ffmpeg'))"` from the project venv. If ffmpeg is missing or not on PATH for uvicorn, we have root cause.
- expecting: `where ffmpeg` returns nothing OR returns a path the uvicorn process cannot see → confirms hypothesis. Server-side fix is to install ffmpeg + put on PATH (or vendor a binary path into config).
- next_action: gsd-debugger reads `.venv/Lib/site-packages/whisperx/audio.py` lines 50-70 to confirm cmd, reads `app/audio.py` and `app/api/audio_api.py:104` for context, then runs `where ffmpeg` and `shutil.which('ffmpeg')` to verify.

## Evidence

- timestamp: 2026-05-04T21:54:03Z — Stack trace bottom is `_winapi.CreateProcess` after temp file successfully written. WinError 2 at this point almost always = executable not found, not input file not found.
- timestamp: 2026-05-05T00:00:00Z — Confirmed `whisperx/audio.py:44-61` builds `cmd = ["ffmpeg", "-nostdin", "-threads", "0", "-i", file, "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(sr), "-"]` then calls `subprocess.run(cmd, capture_output=True, check=True)`. cmd[0] is the literal string "ffmpeg" — no absolute path, no env override. PATH lookup is mandatory.
- timestamp: 2026-05-05T00:00:00Z — `where ffmpeg` exits 1 (not on shell PATH). `C:/laragon/www/whisperx/.venv/Scripts/python.exe -c "import shutil; print(shutil.which('ffmpeg'))"` prints `which: None`. The venv's Python (which uvicorn uses) cannot resolve `ffmpeg` at all.
- timestamp: 2026-05-05T00:00:00Z — `find /c/laragon/bin -iname ffmpeg.exe` and `find /c/Users/rolan -iname ffmpeg.exe` both return zero hits. `C:\Program Files\gstreamer\1.0\msvc_x86_64\bin` is on PATH but contains no `ffmpeg.exe`. Binary genuinely is not installed on this machine.
- timestamp: 2026-05-05T00:00:00Z — `app/audio.py` ALSO uses bare `"ffmpeg"` in `convert_video_to_audio` (line 27) — same vulnerability for the video-upload path, not just whisperx.
- timestamp: 2026-05-05T00:00:00Z — `app/api/exception_handlers.py:121-163` already has `infrastructure_error_handler` that maps `InfrastructureError → 503 SERVICE_UNAVAILABLE` with safe public message. Currently the bare `FileNotFoundError` (Python's wrapper around WinError 2) bypasses this and falls through to `generic_error_handler` → 500.

## Eliminated

- Auth/CSRF chain — request reached the endpoint and the temp file was written; logger.info at line 101 fired BEFORE the crash.
- Temp file race / permission — file path was logged successfully; subprocess crash is the executable lookup, not the input arg.
- Filename spaces ("2025-03-22 Greetings.wav") — the temp file was renamed to `tmpif18ig6b.wav` (no spaces) before subprocess invocation.

## Resolution

### Root cause
`ffmpeg.exe` is not installed (or not reachable on PATH) for the uvicorn process. `whisperx.audio.load_audio` and `app/audio.py:convert_video_to_audio` both invoke `subprocess.run(["ffmpeg", ...])` with bare executable name; on Windows, when `_winapi.CreateProcess` cannot resolve `ffmpeg` via PATH it raises `FileNotFoundError([WinError 2] ...)`. Python’s subprocess does NOT distinguish "input file missing" from "executable missing" in the WinError code — the message is identical.

### Fix
**Two-part fix recommended:**

1. **Install ffmpeg (environmental, REQUIRED):**
   - Recommended: `winget install Gyan.FFmpeg` (puts `ffmpeg.exe` on user PATH after shell relaunch), OR
   - Manual: download static build from https://www.gyan.dev/ffmpeg/builds/, extract to `C:\ffmpeg\`, add `C:\ffmpeg\bin` to system PATH, restart the uvicorn process so it picks up the new PATH.
   - Verify: `where ffmpeg` should print a path; `C:/laragon/www/whisperx/.venv/Scripts/python.exe -c "import shutil; print(shutil.which('ffmpeg'))"` should print that same path.

2. **Code guardrail (recommended, separate commit):**
   - Add a startup probe in `app/audio.py` (module-level or lazy) that calls `shutil.which("ffmpeg")` and caches the result. Wrap `process_audio_file` and `convert_video_to_audio` so that a missing-ffmpeg condition raises `InfrastructureError("ffmpeg binary not found on PATH; install ffmpeg and restart the server", code="FFMPEG_MISSING")` BEFORE invoking subprocess. That maps cleanly to 503 with a clear `code` and correlation_id, instead of the opaque 500 INTERNAL_ERROR.
   - Optional: also catch `FileNotFoundError` from `subprocess.run` inside the wrapper as a defensive belt-and-suspenders, since some PATH races can defeat the startup probe.

### Status
RESOLVED (option 2: env + guardrail).

### Applied
- **Code guardrail (this session):** `app/audio.py` now imports `shutil` + `functools.lru_cache` and `app.core.exceptions.InfrastructureError`. Added module-level `_ffmpeg_path()` (lru_cache=1) wrapping `shutil.which("ffmpeg")` and `_require_ffmpeg()` raising `InfrastructureError("ffmpeg binary not found on PATH; install ffmpeg and restart the server", code="FFMPEG_MISSING")` when None. Both `process_audio_file` and `convert_video_to_audio` call `_require_ffmpeg()` BEFORE subprocess. `infrastructure_error_handler` (`app/api/exception_handlers.py:121-163`) maps to 503 with safe public message + `FFMPEG_MISSING` code + correlation_id. TUS path (`upload_session_service.start_transcription`) re-raises so guardrail surfaces correctly. Tests not impacted — `test_free_tier_gate.py` monkey-patches `process_audio_file`. Smoke test: `python -c "from app.audio import _require_ffmpeg, _ffmpeg_path"` imports clean.
- **Environmental (user):** `winget install Gyan.FFmpeg` ran successfully — installed to `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-8.1-full_build\bin\ffmpeg.exe`. Winget link aliases at `%LOCALAPPDATA%\Microsoft\WinGet\Links` were not yet on PATH in the snapshot shell. **User must restart uvicorn from a new terminal** (or sign out/in once) so the uvicorn child process inherits the updated PATH and `shutil.which("ffmpeg")` returns the binary path.

### Files changed
- `app/audio.py` — added shutil/lru_cache imports + `_ffmpeg_path()` + `_require_ffmpeg()` + guard calls in both audio-processing entry points.

### Verification (post-restart, by user)
1. `where ffmpeg` in a NEW terminal → prints path.
2. From repo root: `.venv/Scripts/python.exe -c "from app.audio import _ffmpeg_path; print(_ffmpeg_path())"` → prints path (not None).
3. Restart uvicorn, retry the audio upload + the TUS video upload that previously 500'd.
4. If ffmpeg ever uninstalls / PATH breaks again: 503 + `FFMPEG_MISSING` (clean) instead of 500 + opaque `INTERNAL_ERROR`.
