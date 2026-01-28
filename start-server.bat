@echo off
echo Starting WhisperX FastAPI Server...
echo.
echo Access the API at: http://localhost:8000
echo Swagger UI docs at: http://localhost:8000/docs
echo.
call .venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
