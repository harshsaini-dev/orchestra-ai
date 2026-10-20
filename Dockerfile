FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGENTFLOW_DB=/app/data/agentflow.db
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 orchestra
COPY --chown=orchestra:orchestra app ./app
COPY --chown=orchestra:orchestra static ./static
COPY --chown=orchestra:orchestra data/policies.json ./data/policies.json
RUN chown -R orchestra:orchestra /app/data
USER orchestra
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
