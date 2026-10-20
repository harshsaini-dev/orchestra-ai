@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  goto fail
)
".venv\Scripts\python.exe" -c "import fastapi,uvicorn,httpx,sqlalchemy,multipart,openpyxl,docx,pypdf,reportlab,apscheduler" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
echo OrchestraAI: open http://127.0.0.1:8000 in your browser.
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto fail
exit /b 0
:fail
echo Startup failed. Read the error above. See README.md troubleshooting.
pause
exit /b 1
