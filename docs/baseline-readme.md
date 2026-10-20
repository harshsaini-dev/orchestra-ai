# AgentFlow — MCA progress milestone

**Project title:** Design and Development of a Multi-Agent AI System for Intelligent Business Workflow Automation.

**Student:** Harsh Saini · Roll 253028036 · MCA III Semester · COER University · Session 2026–27.

AgentFlow is a local, controlled prototype for e-commerce order exceptions. It reads an order, retrieves policies, proposes a decision, asks for human approval where required, executes a permitted simulated action, and records an audit trail.

For a public PC/mobile link, follow [DEPLOY_RENDER.md](DEPLOY_RENDER.md). The deployment uses the included Dockerfile, Render Blueprint and persistent disk; add the Gemini key only in Render's secret environment settings.

Version **0.7.0** names this milestone. It is **not** a measured claim of 50% project completion.

## Start on Windows

Requires Python **3.10 or newer** (tested here on 3.12). Extract the ZIP first. Keep the complete `agentflow` folder together.

**Easiest:** double-click `start.bat`. It creates a virtual environment and installs dependencies on first use. Open **http://127.0.0.1:8000**. Keep the terminal open.

**PowerShell alternative**, from inside the `agentflow` folder:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Activation is optional, so no PowerShell execution-policy change is needed. On macOS/Linux, use `bash start.sh`.

The first dependency installation needs internet. The dashboard, local policies, database and offline workflow need no network after installation. Swagger at `/docs` may need internet for its external UI assets; use the dashboard for the offline practical.

## Five-minute practical demonstration

1. Open **Live console**. The default mode works without an API key.
2. Click **Cancellation**, keep **Presentation pace** enabled, and click **Start workflow**.
3. Watch Planner → Data → Policy → Decision. Each agent shows its actual start/completion state. Action waits for review.
4. Click **Policy** in the agent map, expand **Output & evidence**, and explain the retrieved policy IDs.
5. Enter a reviewer name below the map, then click **Approve & execute**. Watch Action run, then compare the original snapshot and current order.
6. Click **Inspect past steps** to replay recorded events. This never runs an action again. Return to the full trace afterward.
7. Open **Run history**, filter statuses, reopen a run, and export CSV or download its JSON audit.
8. For escalation, select ORD-1002 and operation Cancel order. For rejection, choose **Refund**, run it, and click **Reject action**.

See `docs/DEMO_AND_VIVA.md` for explanations and questions.

## New in v0.7: document RAG

For full setup and practical steps, read **RAG_SETUP.md**. On Windows:

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` locally.
2. Run **start_rag.bat**. It installs the additional ChromaDB/PDF dependencies.
3. Open **RAG knowledge** and click **Build vector index**. Four governing policies are already chunked.
4. Ask a question using **Retrieve & generate**; expand the returned sources.
5. In **Live console**, enable **Document RAG**, then run a workflow to see retrieval and generation inside the agent trace.

`start.bat` remains the smaller, offline-only installation path. RAG dependencies are optional so the original demonstration stays usable on low-resource machines. A full RAG run needs internet and Gemini access. The embedding model runs through the provider API, not as a local model download.

## New in v0.6: live operations console

- Genuine server-sent events: running, completed, skipped and awaiting-approval states.
- Clickable agent inspector: actual input/output, policy excerpts and measured compute duration.
- Persisted execution traces: reconnect after browser refresh, with event IDs preventing duplicates.
- Historical step replay: scrub through recorded events without re-executing a workflow.
- Human checkpoint: approval queue, state/policy revalidation, snapshot/current-order comparison.
- Searchable, status-filtered history, CSV export and JSON audit export.
- Two local worker threads with a bounded queue (eight total active/queued jobs); stop planning at an agent boundary.
- A redesigned responsive workspace and an in-app **How it works** page.

**Presentation pace** deliberately waits 0.8 seconds before each agent executes, so a practical examiner can follow the hand-offs. Switch it off for normal speed. Per-agent compute duration excludes this pause; it is measured, not a generated confidence score.

Run **one Uvicorn worker only**. Active jobs are stored but not automatically retried after a server restart: unfinished jobs are marked interrupted. Review the existing workflow history before retrying. Stop affects planning at the next agent boundary, not an in-progress approval transaction. A pending external model call may need to finish or time out first.

To update an existing installation, stop its server. Extract this package into a separate folder. For clean demo data, start it as-is. To retain existing history, copy the old `data/agentflow.db` into the new `data` folder **after shutting down the old server**; the new job tables are added automatically. Keep a backup. Older workflows have business audits but no retroactively generated live traces.

## Implemented in this package

| Module | Actual behaviour |
|---|---|
| Dashboard | Live agent map, input/output inspector, event stream, replay, approvals, history filters, CSV and JSON exports |
| Planner Agent | Explicit intent or conservative keyword classification; optional Gemini classification |
| Data Agent | Allowlisted `get_order_status` tool and parameterised database reads |
| Policy Agent | BM25 lexical ranking, intent routing, policy IDs and SHA-256 policy fingerprint |
| Decision Agent | Deterministic eligibility checks and proposed action; optional Gemini advisory explanation |
| Action Agent | Allowlisted cancellation/refund tools, mandatory recorded approval, transactional writes |
| Orchestrator | Structured hand-offs and persistent workflow records; resume from pending approval |
| SQLite | Orders, workflows, events, approvals, simulated refunds, jobs and job_events |
| Execution controls | Input validation, idempotency keys, duplicate-refund protection, state/version rechecks, rollback |
| API | FastAPI REST endpoints, OpenAPI schema and Swagger |
| Verification | 87 automated tests (with RAG dependencies) at package creation, including 32 seeded-order/intent scenarios |

### Honest AI/RAG description

The default offline flow is **rule-based multi-agent orchestration**, not an autonomous LLM system. Its agent roles are Python components with separate responsibilities. They do not each run a separate language model.

Offline business decisions still use the curated policy rules. **Document RAG** now adds Gemini semantic embeddings, a persistent ChromaDB collection, and generated answers using retrieved excerpts with source references. It is explicitly enabled; it is not available without a configured provider key and a built index.

The RAG knowledge tab accepts text-based PDF, TXT and Markdown uploads. It chunks text with overlap, preserves PDF page numbers, indexes only missing chunks, retrieves nearest passages, and validates generated source IDs and exact quotes. This citation check does not prove every statement is semantically entailed.

Live order workflows can enable **Document RAG** for a retrieved-policy explanation in the Decision Agent. Only governing policy documents are eligible for that path. Supplementary uploads are available to knowledge Q&A but cannot grant tools, change action rules or bypass approval.

**No live Gemini API call was verified during this build.** Real Chroma/SQLite and browser integration were tested using explicit provider test doubles. Configure your own key and test indexing plus generation before presenting live RAG.

## Optional Gemini configuration

Copy `.env.example` to `.env` in the project root, then set:

```dotenv
GEMINI_API_KEY=your_actual_key
GEMINI_MODEL=gemini-3.8-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
```

Use a `generateContent` model that is actually enabled in your Google AI Studio account; the example name is configurable. Restart the server and tick **Gemini assistance**. A configured key does not prove network access, quota or model availability. Errors fall back to offline rules and are visible in the workflow record.

The optional provider receives the request for classification and synthetic order/policy data for explanation. The API key stays on the server and must never be committed or pasted into screenshots. `.env` is excluded by `.gitignore`.

The model cannot approve a refund, access arbitrary tools or override eligibility. Its explanation is explicitly advisory.

## Test and CLI demo

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.demo
```

The CLI demo uses a temporary database and does not change dashboard records. The tests use temporary databases. Install `requirements-rag.txt` as well to run all 87 tests; otherwise the optional RAG test module is skipped. A Starlette warning about its `httpx` TestClient compatibility may appear with the tested versions; it did not prevent the test suite passing.

The sample dates are generated on the database's first start. If you need a fresh demonstration later, stop the server and run:

```powershell
.\.venv\Scripts\python.exe -m scripts.reset_demo --confirm
```

This creates a timestamped database backup before resetting the sample data. Start the server again. Do not run reset while the server is active.

## API example

`POST /api/workflows`

```json
{
  "order_id": "ORD-1001",
  "message": "My order is delayed. Please cancel it.",
  "intent": "cancel",
  "use_gemini": false,
  "use_rag": false,
  "request_key": "practical-demo-001"
}
```

The same request key with the same payload returns the existing workflow. Reusing a key with changed input returns HTTP 409. Omit it when intentionally creating a new request.

`POST /api/workflows/{workflow_id}/review`

```json
{"approve": true, "reviewer": "Harsh Saini", "note": "Checked policy and order"}
```

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/rag/status` | Configuration, document list and index counts |
| POST | `/api/rag/documents` | Upload `{filename, content_base64}` and chunk locally |
| GET | `/api/rag/documents/{id}/chunks` | Inspect extracted text and page metadata |
| DELETE | `/api/rag/documents/{id}` | Remove a supplementary upload |
| POST | `/api/rag/index` | Embed new chunks and build/update Chroma |
| POST | `/api/rag/retrieve` | Retrieve context for `{question, scope, top_k}` |
| POST | `/api/rag/ask` | Retrieve then generate a cited answer |
| POST | `/api/jobs` | Queue `{request: {...}, guided: true}`; returns job ID immediately |
| GET | `/api/jobs/{id}` | Persisted status and progress events |
| GET | `/api/jobs/{id}/events` | SSE stream; `after` cursor / Last-Event-ID supported |
| POST | `/api/jobs/{id}/stop` | Stop planning at the next boundary |
| GET | `/api/workflows/{id}/jobs` | Execution traces for a workflow |
| POST | `/api/workflows/{id}/review-job` | Queue `{review: {approve, reviewer, note}, guided: true}` |
| GET | `/api/health` | Mode, configuration and version |
| GET | `/api/metrics` | Workflow and audit counts |
| GET | `/api/orders` | Order database |
| GET | `/api/orders/{order_id}` | Read a single order |
| GET | `/api/policies?q=refund` | Search policy documents |
| POST | `/api/workflows` | Plan and evaluate a request |
| GET | `/api/workflows` | Latest 100 workflows |
| GET | `/api/workflows/{id}` | Decision, evidence and trace |
| POST | `/api/workflows/{id}/review` | Approve or reject |
| GET | `/api/workflows/{id}/export` | Download JSON audit record |

## Project structure

- `app/main.py`: HTTP API, local boundary checks and static dashboard.
- `app/models.py`: input contracts and domain errors.
- `app/database.py`: schema, seed data and persistence.
- `app/agents.py`: five agent roles and business eligibility.
- `app/retrieval.py`: lexical policy index.
- `app/gemini.py`: optional provider adapter.
- `app/service.py`: orchestration, approvals and transactions.
- `app/jobs.py`: bounded background queue, persisted progress, cancellation and restart handling.
- `app/rag.py`: document extraction, chunk storage, semantic retrieval and cited generation.
- `data/rag/`: generated RAG storage (not included in the ZIP).
- `data/policies.json`: trusted synthetic business policies.
- `static/`: HTML, CSS and browser JavaScript; no build step or CDN.
- `tests/`: automated business and integration tests.
- `scripts/`: offline demo and explicit reset utility.
- `docs/`: progress evidence, architecture, viva notes and verification results.

## Limits and next milestones

This is a **single-machine academic prototype**. It binds to localhost. Reviewer names are self-declared; authentication and role-based access are not implemented. Do not expose it to a public network. The audit log is a database record, not a tamper-proof compliance system. All order data and money transfers are simulated.

Pending work: authenticated users and approval roles; live Gemini evaluation; retrieval-quality evaluation on a larger corpus; automatic recovery/retries and distributed scheduling beyond the local worker queue; real service integrations in a sandbox; broader evaluation and deployment hardening.

## Troubleshooting

- **`python` not found:** install Python and enable “Add Python to PATH”, or replace `python` with `py` when creating the environment.
- **`No module named app`:** open the terminal in the folder that contains `app`, `static` and `requirements.txt`.
- **Port 8000 already in use:** stop the older server with Ctrl+C, or use `--port 8001` and open that port.
- **Browser cannot connect:** the server terminal must remain open; wait for “Application startup complete”.
- **Scenario already completed:** this is expected persistence. Use another eligible order or reset after stopping the server.
- **Gemini fails:** keep the default offline mode for the practical; confirm the account's model name, key and quota separately.
- **Installation fails:** save the full terminal error; avoid changing package versions randomly just before the practical.

## References

- FastAPI testing: https://fastapi.tiangolo.com/tutorial/testing/
- FastAPI static files: https://fastapi.tiangolo.com/tutorial/static-files/
- Gemini generateContent: https://ai.google.dev/api/generate-content

Prepared with AI assistance. Review the code and rehearse the explanation before presenting it as your project progress.
