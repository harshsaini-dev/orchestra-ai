"""Run with python -m uvicorn app.main:app --host 127.0.0.1 --port 8000."""

import json
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .database import Database
from .models import (
    ApprovalRequest,
    DomainError,
    WorkflowRequest,
    JobRequest,
    ReviewJobRequest,
    DocumentUpload,
    RagQuestion,
)
from .jobs import JobManager, TERMINAL
from .retrieval import PolicyIndex
from .service import WorkflowService
from .rag import RagEngine

ROOT = Path(__file__).resolve().parent.parent


def load_environment():
    """Load only our known settings. Environment variables take precedence."""
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key.strip() in {
                "GEMINI_API_KEY",
                "GEMINI_MODEL",
                "GEMINI_EMBEDDING_MODEL",
                "AGENTFLOW_DB", "AGENTFLOW_ALLOWED_HOSTS", "OPENAI_API_KEY", "OPENAI_MODEL",
                "OLLAMA_MODEL", "ORCHESTRA_LLM_PROVIDER", "ORCHESTRA_DENSE",
                "ORCHESTRA_EMBED_MODEL_PATH", "ORCHESTRA_SECURE_COOKIE", "ORCHESTRA_DISABLE_SIGNUP",
            }:
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def create_app(db_path=None, policy_path=None, gemini=None):
    load_environment()
    db = Database(
        db_path or os.getenv("AGENTFLOW_DB", str(ROOT / "data" / "agentflow.db"))
    )
    index = PolicyIndex(Path(policy_path or ROOT / "data" / "policies.json"))
    service = WorkflowService(db, index, gemini)
    rag = RagEngine(
        db.path.parent / "rag",
        index,
        service.gemini,
        os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
    )
    service.rag = rag
    jobs = JobManager(db, service)
    from .workspace.store import Store
    from .workspace.engine import Engine
    from .workspace.api import make_router, tick_schedules
    from apscheduler.schedulers.background import BackgroundScheduler
    workspace = Store(db.path.parent / "workspace.db")
    runner = Engine(workspace)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(tick_schedules, "interval", seconds=30, args=[workspace, runner], max_instances=1, coalesce=True)

    @asynccontextmanager
    async def lifespan(application):
        db.initialize()
        jobs.initialize()
        rag.initialize()
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown(wait=True)
            runner.shutdown()
            workspace.engine.dispose()
            jobs.shutdown()

    api = FastAPI(
        title="OrchestraAI",
        version="1.0.0",
        lifespan=lifespan,
        description="Authenticated multi-company academic workflow system. Financial operations are simulated.",
    )
    api.state.workspace, api.state.runner = workspace, runner
    api.include_router(make_router(workspace, runner))
    api.state.db, api.state.service = db, service
    api.state.jobs = jobs
    api.state.rag = rag
    allowed_hosts = [
        host.strip()
        for host in os.getenv(
            "AGENTFLOW_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"
        ).split(",")
        if host.strip()
    ]
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @api.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.url.path != "/api/health" and os.getenv("ORCHESTRA_LEGACY") != "1":
            return JSONResponse({"detail": "Legacy sandbox API is disabled. Use authenticated /v1 routes."}, status_code=410)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            parsed = urlparse(origin)
            if parsed.scheme not in {
                "http",
                "https",
            } or parsed.netloc != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "Cross-origin mutation blocked."}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith(("/api/", "/v1/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @api.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"detail": error.message}, status_code=error.status)

    @api.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(ROOT / "static" / ("index.html" if os.getenv("ORCHESTRA_LEGACY") == "1" else "workspace.html"))

    @api.get("/api/health", tags=["System"])
    def health():
        return {
            "status": "ok",
            "version": "1.0.0",
            "default_mode": "offline_rules",
            "gemini_configured": service.gemini.configured,
            "gemini_model": getattr(service.gemini, "model", "test-adapter"),
            "simulation": True,
            "policy_count": len(index.load()[0]),
        }

    @api.get("/api/metrics", tags=["System"])
    def metrics():
        return db.metrics()

    @api.post("/api/jobs", status_code=202, tags=["Live execution"])
    def create_job(body: JobRequest):
        return jobs.submit("run", body.request, body.guided)

    @api.get("/api/jobs/{job_id}", tags=["Live execution"])
    def get_job(job_id: str):
        return jobs.get(job_id)

    @api.post("/api/jobs/{job_id}/stop", tags=["Live execution"])
    def stop_job(job_id: str):
        return jobs.stop(job_id)

    @api.get("/api/workflows/{workflow_id}/jobs", tags=["Live execution"])
    def workflow_jobs(workflow_id: str):
        get_workflow(workflow_id)
        return jobs.for_workflow(workflow_id)

    @api.post(
        "/api/workflows/{workflow_id}/review-job",
        status_code=202,
        tags=["Live execution"],
    )
    def review_job(workflow_id: str, body: ReviewJobRequest):
        workflow = get_workflow(workflow_id)
        if workflow["status"] != "pending_approval":
            raise DomainError("Only a pending workflow can be reviewed.", 409)
        return jobs.submit("review", body.review, body.guided, workflow_id)

    @api.get("/api/jobs/{job_id}/events", tags=["Live execution"])
    async def stream_events(job_id: str, request: Request, after: int = Query(0, ge=0)):
        jobs.get(job_id)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise DomainError("Invalid event cursor.")

        async def stream():
            last = cursor
            heartbeat = 0
            while not await request.is_disconnected():
                # Read status first so terminal state cannot hide a final event.
                terminal = jobs.get(job_id)["status"] in TERMINAL
                for event in jobs.events(job_id, last):
                    last = event["id"]
                    yield f"id: {last}\ndata: {json.dumps(event)}\n\n"
                if terminal:
                    break
                heartbeat += 1
                if heartbeat % 80 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.12)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    @api.get("/api/traces/{trace_id}", tags=["Live execution"])
    def trace(trace_id: str):
        return service.traces.get(trace_id)

    @api.get("/api/workflows/{workflow_id}/traces", tags=["Live execution"])
    def workflow_traces(workflow_id: str):
        get_workflow(workflow_id)
        return service.traces.for_workflow(workflow_id)

    @api.get("/api/orders", tags=["Orders"])
    def orders():
        return db.orders()

    @api.get("/api/orders/{order_id}", tags=["Orders"])
    def order(order_id: str):
        return service.data.invoke("get_order_status", db, order_id)

    @api.get("/api/policies", tags=["Knowledge"])
    def policies(q: str = Query(default="", max_length=500)):
        if q:
            return index.search(q, limit=4)[0]
        return index.load()[0]

    @api.get("/api/rag/status", tags=["Document RAG"])
    def rag_status():
        return rag.status()

    @api.post("/api/rag/documents", status_code=201, tags=["Document RAG"])
    def rag_upload(body: DocumentUpload):
        return rag.ingest(body.filename, body.content_base64)

    @api.get("/api/rag/documents/{document_id}/chunks", tags=["Document RAG"])
    def rag_chunks(document_id: str):
        rows = [r for r in rag.rows() if r["document_id"] == document_id]
        if not rows:
            raise DomainError("Document not found.", 404)
        return rows

    @api.delete("/api/rag/documents/{document_id}", tags=["Document RAG"])
    def rag_remove(document_id: str):
        return rag.remove(document_id)

    @api.post("/api/rag/index", tags=["Document RAG"])
    def rag_build():
        return rag.build()

    @api.post("/api/rag/retrieve", tags=["Document RAG"])
    def rag_retrieve(body: RagQuestion):
        return rag.retrieve(body.question, body.scope, body.top_k)

    @api.post("/api/rag/ask", tags=["Document RAG"])
    def rag_ask(body: RagQuestion):
        return rag.ask(body.question, body.scope, body.top_k)

    @api.get("/api/workflows", tags=["Workflows"])
    def workflows():
        return db.workflows()

    @api.post("/api/workflows", status_code=201, tags=["Workflows"])
    def create_workflow(body: WorkflowRequest):
        return service.create(body)

    @api.get("/api/workflows/{workflow_id}", tags=["Workflows"])
    def get_workflow(workflow_id: str):
        result = db.workflow(workflow_id)
        if result is None:
            raise DomainError("Workflow not found.", 404)
        return result

    @api.post("/api/workflows/{workflow_id}/review", tags=["Approvals"])
    def review(workflow_id: str, body: ApprovalRequest):
        return service.review(workflow_id, body)

    @api.get("/api/workflows/{workflow_id}/export", tags=["Audit"])
    def export(workflow_id: str):
        result = get_workflow(workflow_id)
        result["message_traces"] = service.traces.for_workflow(workflow_id)
        traces = jobs.for_workflow(workflow_id)
        if traces:
            result["execution_jobs"] = traces
        return Response(
            json.dumps(result, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{result["id"]}.json"'
            },
        )

    api.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return api


app = create_app()
