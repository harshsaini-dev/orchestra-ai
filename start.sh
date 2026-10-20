#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
if ! .venv/bin/python -c 'import fastapi,uvicorn,httpx,sqlalchemy,multipart,openpyxl,docx,pypdf,reportlab,apscheduler' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
