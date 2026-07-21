@echo off
echo Starting WhisperX FastAPI Server...
echo.
echo Access the API at: http://localhost:8000
echo Swagger UI docs at: http://localhost:8000/docs
echo.

REM Get the directory where this script lives (project root)
set "SCRIPT_DIR=%~dp0"

REM FFmpeg 7.1 SHARED build, PINNED (matches start-server-boot.bat).
REM Winget auto-discovery would find the 8.1 static build and break torchcodec
REM (whisperX main needs FFmpeg 4-7 shared DLLs). Same dir ships ffmpeg.exe.
REM app/core/dll_paths.py also reads FFMPEG_DIR for os.add_dll_directory.
set "FFMPEG_DIR=C:\tools\ffmpeg-7.1-shared\bin"
set "PATH=%FFMPEG_DIR%;%PATH%"

if not exist "%FFMPEG_DIR%\ffmpeg.exe" (
    echo WARNING: %FFMPEG_DIR%\ffmpeg.exe not found - audio processing will fail.
)

REM Activate venv using absolute path
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

REM Run uvicorn from project root
cd /d "%SCRIPT_DIR%"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
