@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r requirements-rag.txt
if errorlevel 1 goto fail
if not exist ".env" copy ".env.example" ".env" >nul
echo Set GEMINI_API_KEY in .env before starting for live RAG.
echo Open http://127.0.0.1:8000 and select RAG knowledge.
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto fail
exit /b 0
:fail
echo Read the error above. Core offline mode is still available through start.bat.
pause
exit /b 1
