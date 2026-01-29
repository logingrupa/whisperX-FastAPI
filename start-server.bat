@echo off
echo Starting WhisperX FastAPI Server...
echo.
echo Access the API at: http://localhost:8000
echo Swagger UI docs at: http://localhost:8000/docs
echo.

REM Get the directory where this script lives (project root)
set "SCRIPT_DIR=%~dp0"

REM Add ffmpeg to PATH (winget installs to user-specific location)
set "WINGET_PKGS=%LOCALAPPDATA%\Microsoft\WinGet\Packages"

REM Search winget packages folder for ffmpeg using dir
for /f "delims=" %%i in ('dir /b /s "%WINGET_PKGS%\ffmpeg.exe" 2^>nul') do (
    set "PATH=%%~dpi;%PATH%"
    echo ffmpeg found: %%~dpi
    goto :ffmpeg_done
)

echo WARNING: ffmpeg not found in WinGet packages.
echo Checking system PATH...
where ffmpeg >nul 2>&1 && echo ffmpeg found in system PATH || echo ffmpeg NOT found - video processing will fail.

:ffmpeg_done

REM Activate venv using absolute path
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

REM Run uvicorn from project root
cd /d "%SCRIPT_DIR%"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
