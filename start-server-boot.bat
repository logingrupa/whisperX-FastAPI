@echo off
REM ---------------------------------------------------------------------------
REM Boot launcher for the WhisperX FastAPI backend (Scheduled Task, RU SYSTEM).
REM Differs from start-server.bat (manual/dev) on purpose:
REM   - ffmpeg dir is PINNED absolute (SYSTEM profile has no winget %LOCALAPPDATA%)
REM   - NO --reload (stable long-run; reload watcher is a dev convenience)
REM   - stdout/stderr appended to logs\backend-boot.log (no console attached)
REM   - PREFLIGHT frees port %PORT%: finds any stale LISTENING owner, walks up
REM     to the root python of that process tree and taskkill /T's it, so a
REM     re-run or task re-trigger (e.g. after a code patch) always rebinds
REM     cleanly instead of dying with WinError 10013/10048. First boot = no-op.
REM   - PREFLIGHT then verifies the OS still reserves %PORT% for us. WinNAT can
REM     claim the port with no owning process, which the kill above cannot fix.
REM   - PREFLIGHT logs to its OWN file. The dying server holds backend-boot.log,
REM     and cmd skips a command outright when its redirect cannot open, so
REM     preflight silently never ran and its exit code was lost.
REM Config + secrets load from .env (pydantic env_file), resolved from cwd, so
REM   the cd below is REQUIRED for the app to find .env and records.db.
REM ---------------------------------------------------------------------------
setlocal
set "SCRIPT_DIR=%~dp0"
set "PORT=8000"
REM FFmpeg 7.1 SHARED build (BtbN) — torchcodec (whisperX main) links against
REM FFmpeg 4-7 shared DLLs; the old winget 8.1 static build fails both axes.
REM Same dir ships ffmpeg.exe, so whisperx.load_audio's subprocess keeps working.
REM app/core/dll_paths.py also reads FFMPEG_DIR for os.add_dll_directory.
set "FFMPEG_DIR=C:\tools\ffmpeg-7.1-shared\bin"
set "PATH=%FFMPEG_DIR%;%PATH%"

REM HuggingFace cache is PINNED for the same reason ffmpeg is: running as
REM SYSTEM, %USERPROFILE% resolves to C:\Windows\System32\config\systemprofile,
REM so the service gets an empty second cache and re-downloads every model.
REM Gated pyannote/speaker-diarization-3.1 fails there, from_pretrained returns
REM None, and diarization dies at 60%%. Point it at the desktop user's cache.
set "HF_HOME=C:\Users\rolan\.cache\huggingface"

REM nltk data pinned for the same SYSTEM-profile reason: punkt_tab (whisperX
REM main sentence splitting) was downloaded to the desktop user's Roaming dir.
set "NLTK_DATA=C:\Users\rolan\AppData\Roaming\nltk_data"

REM Never contact the HF hub at runtime. Every model is already cached (whisper
REM large-v3 + tiny, lv/ru/en align models, all three pyannote models); the hub
REM call was only a revision revalidation, and when it failed it surfaced as
REM "pyannote/speaker-diarization-3.1 unavailable" and killed diarization even
REM though the weights were on disk. Verified 2026-07-22: all 6 models load with
REM the hub disabled.
REM CAUTION: adding a NEW language fails hard here instead of downloading its
REM align model. To add one: comment this out, run one job to warm the cache,
REM then re-enable.
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"

REM Two jobs on the GPU at once. Was 1 while disk I/O was the bottleneck (models
REM read at 14 MB/s under Defender scanning, so the GPU sat at 1-8% and extra
REM concurrency bought nothing). With the model dirs excluded from Defender the
REM loads dropped to 1-6 s and the GPU is idle again for a different reason:
REM there is simply only one job. 24 GB VRAM holds ~4 GB per job comfortably.
REM Revert to 1 if CUDA OOM or driver hangs appear.
set "GPU_MAX_CONCURRENT_JOBS=2"

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

set "PREFLIGHT_LOG=%SCRIPT_DIR%logs\preflight.log"

REM --- Preflight: free port %PORT% by killing any stale server tree ---
echo [%DATE% %TIME%] preflight: freeing port %PORT% >> "%PREFLIGHT_LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=%PORT%;$owners=@((Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue).OwningProcess)|Select-Object -Unique;foreach($o in $owners){if(-not $o){continue};$cur=$o;while($true){$pr=Get-CimInstance Win32_Process -Filter ('ProcessId='+$cur) -EA SilentlyContinue;if(-not $pr){break};$par=Get-CimInstance Win32_Process -Filter ('ProcessId='+$pr.ParentProcessId) -EA SilentlyContinue;if($par -and $par.Name -eq 'python.exe'){$cur=$par.ProcessId}else{break}};Write-Output ('killing stale python tree root PID '+$cur);taskkill /F /T /PID $cur}" >> "%PREFLIGHT_LOG%" 2>&1

REM brief pause so the socket fully releases before we rebind
ping -n 3 127.0.0.1 >nul

call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
cd /d "%SCRIPT_DIR%"

REM --- Preflight: port %PORT% must not be OS-reserved (WinNAT block, no PID to kill) ---
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\ensure-port-8000.ps1" -Port %PORT% >> "%PREFLIGHT_LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] aborting: port %PORT% unavailable (see reason above) >> "%PREFLIGHT_LOG%"
    exit /b 1
)

echo [%DATE% %TIME%] boot launcher starting uvicorn >> "%SCRIPT_DIR%logs\backend-boot.log"
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% >> "%SCRIPT_DIR%logs\backend-boot.log" 2>&1
