@echo off
echo Starting WhisperX Frontend (Vite dev server)...
echo.
echo Access at: http://localhost:5173/ui
echo.

set "SCRIPT_DIR=%~dp0"

set "BUN_EXE=%USERPROFILE%\.bun\bin\bun.exe"
if not exist "%BUN_EXE%" set "BUN_EXE=bun"

cd /d "%SCRIPT_DIR%"
"%BUN_EXE%" run dev
