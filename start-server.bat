@echo off
echo Starting WhisperX FastAPI Server...
echo.
echo Access the API at: http://localhost:8000
echo Swagger UI docs at: http://localhost:8000/docs
echo.

REM Get the directory where this script lives (project root)
set "SCRIPT_DIR=%~dp0"

REM Activate venv using absolute path
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

REM Run uvicorn from project root
cd /d "%SCRIPT_DIR%"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
