#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-rag.txt
if [ ! -f .env ]; then cp .env.example .env; fi
echo 'Set GEMINI_API_KEY in .env for live RAG. Open http://127.0.0.1:8000'
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
