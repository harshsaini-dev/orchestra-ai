# OrchestraAI

**Design and Development of a Multi-Agent AI System for Intelligent Business Workflow Automation**

A runnable academic project built with Python, FastAPI, SQLAlchemy/SQLite, and plain HTML/CSS/JavaScript. It combines company records, cited document retrieval, versioned business rules, approval-gated actions, and a live agent workspace. The default demonstration runs offline after dependencies are installed; no paid API is required.

## Start on Windows

Install Python 3.11 or newer. Extract this project, open PowerShell in its `orchestra-ai` folder, and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000**. Create an account with a password of at least 10 characters, create a company workspace, and click **Load demo data**. Then click **Scan workspace**. There are no shared default credentials.

The included `start.bat` can create the virtual environment and install missing dependencies. No PowerShell activation or execution-policy change is necessary. Keep the terminal open while using the app. Press Ctrl+C to stop.

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

## What is implemented

| Area | Working behavior |
|---|---|
| Company workspaces | Authenticated accounts, server-resolved Owner/Manager/Analyst memberships, tenant-scoped object queries |
| Data hub | CSV/XLSX records; PDF/DOCX/TXT/MD sources; actual upload progress; schema, missing cells, duplicates, numeric outliers, and date profiles |
| Synthetic business | 1,180 records, 12 months of sales, six datasets, and a 12-page handbook; deliberate operational and data-quality defects |
| Retrieval | Heading-aware chunks with 40-word overlap; BM25 + TF-IDF cosine, reciprocal rank fusion, lexical reranking, citations, passage viewer, abstention and phrase-based injection flags |
| Policies | Explicit refund, discount, inventory, overdue, and leave rules; Owner publication, source versions, revision history, conservative text-to-draft extraction and within-source conflict flags |
| Simulation | Current versus proposed decisions, affected records and their value; an audited impact report, with no invented savings |
| Fixes | Review/approve/reject, informed record editing, version guards, idempotent repeat approval, and transaction-local postcondition verification |
| Autopilot | Explicit run-on-enable whitespace cleanup only; all other record and financial actions require human review |
| Agents | Orchestrator, Enquiry, Data, Policy, Task, Report, Notification and Auditor; typed bus envelopes and state transitions |
| Execution | Two worker threads, ten outstanding slots, persisted events, SSE reconnect, replay, handler timing, fail-once read recovery and interrupted-run marking |
| Reporting | Weekly sales window, published reports, PDF download, internal notifications, persisted APScheduler interval configuration |
| Accountability | Actor/input/policy/action audit evidence, previous-hash chain, verification endpoint, transparent heuristic health score |
| Interface | Ten responsive screens, dark/light themes, CSS 3D sculpture, isometric agent network, pointer depth, message packets, reduced-motion support, keyboard inspector, Ctrl+K palette |
| Optional | Browser dictation with explicit consent; local Chroma/sentence-transformer adapter; one provider interface for OpenAI, Gemini and Ollama drafts |

## Five demonstration workflows

1. **Weekly sales:** Data → Report → Auditor → Notification. Aggregates the latest seven days ending at the newest valid sales date in the dataset.
2. **Refund review:** Data → Policy → Task → Auditor proposes reviews. A Manager/Owner inspects the issue and approves a **simulated** refund update.
3. **Inventory planning:** Data → Policy → Task → Auditor proposes low-stock actions. Approval creates a purchase-order draft; stock remains unchanged.
4. **Policy impact:** Data → Policy → Report → Auditor → Notification compares a proposed rule table and publishes the comparison.
5. **Document Q&A:** Enquiry → Auditor retrieves extracts and checks that cited passages exist verbatim in the source.

The additional **Scan business issues** workflow finds duplicates, missing values, whitespace, numeric outliers, policy breaches, stale sources and supported-clause conflicts.

## Repository structure

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI composition, lifespan, same-origin boundary and static delivery |
| `app/core/` | Shared typed message bus, explicit agent states, trace storage and legacy eligibility rules |
| `app/agents/` | Preserved modular agents from the earlier order-workflow milestone |
| `app/workspace/store.py` | SQLAlchemy entities, tenant queries, transactions, sessions and audit chain |
| `app/workspace/api.py` | Workspace endpoints, role checks, exports and scheduler tick |
| `app/workspace/engine.py` | Six DAGs, agent handlers, bounded execution and persisted events |
| `app/workspace/ingestion.py` | Bounded loaders, profiles and chunking |
| `app/workspace/retrieval.py`, `dense.py`, `llm.py` | Offline retrieval and optional adapters |
| `app/workspace/policies.py`, `operations.py` | Structured rules, draft extraction, impact, issues and verified fixes |
| `app/workspace/demo.py`, `evaluation.py` | Reproducible fixtures and measured benchmark |
| `static/workspace.html`, `console.css`, `console.js`, `spatial.js` | Final UI; no frontend build step |
| `tests/` | Backend/security regression tests and DOM/API integration checks |
| `scripts/`, `demo_data/` | Reproducible export/evaluation commands and synthetic source files |
| `docs/` | Architecture, API/events, viva, demonstration script, phase record and verification evidence |

The original order-workflow implementation remains available for regression testing. Its unauthenticated `/api/*` routes are **disabled by default**, except `/api/health`. `ORCHESTRA_LEGACY=1` explicitly enables that isolated legacy sandbox and switches the home page; do not enable it on a shared deployment. The final authenticated application uses `/v1/*`.

## Test and evaluate

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term
.\.venv\Scripts\python.exe -m scripts.evaluate
```

For the optional frontend integration test, install Node 22 or newer:

```powershell
npm ci
$env:ORCHESTRA_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm run test:ui
```

This launches a disposable backend, exercises real HTTP/SSE through a DOM emulator, and removes its temporary database. It is not a browser screenshot or GPU-rendering test. `npm run test:legacy-ui` checks the preserved earlier UI separately.

See `docs/verification.md` for the measured result and limitations. Reproduce synthetic source files with `python -m scripts.generate_demo --out demo_data`.

## Docker

```bash
docker compose up --build
```

The service binds only `127.0.0.1:8000` on the host and stores SQLite data in a named volume. It runs as an unprivileged container user with one Uvicorn worker. `docker compose down` preserves the volume. Do not add `-v` unless you intend to delete its data. Docker was not installed in the verification environment; the configuration is provided but was not built there.

## Optional models

The default is entirely offline. `RAG_SETUP.md` describes opt-in dense retrieval and provider summaries. Model binaries and API credentials are not bundled. Exact offline extracts remain available if an optional provider fails. Generated summaries are labeled drafts and never authorize actions.

## Operational limits

- Financial operations are simulated. No payment, ERP, supplier order or external email is sent.
- SQLite JSON datasets are intended for this bounded academic workload: 10 MB per file, 20,000 rows, 200 PDF pages and 50 MB expanded Office archives. No OCR is included.
- Use **one process**. The queue and transaction lock are local, not distributed. Interrupted jobs remain inspectable and are not automatically replayed after restart.
- The health score is a disclosed issue-count heuristic, not a prediction or business KPI. Creating a PO or escalation does not resolve the underlying condition.
- The text parser recognizes a small documented set of rule phrases. Owners must review exceptions and unsupported language. It is not an arbitrary natural-language policy compiler.
- Reference pages for DOCX/TXT/MD are sections, not invented page numbers. Editing extracted document text creates a text revision and replaces PDF page boundaries.
- Retrieval scores are ranking scores. Citation validity verifies source identity and exact text, not semantic entailment. The small golden benchmark is not a general accuracy claim.
- The hash chain is not tamper-proof against someone who can rewrite the entire database. There is no external trusted anchor.
- Accounts have password hashing, expiring sessions, same-origin mutation checks and role enforcement, but no email verification, password recovery, MFA or distributed rate limiter. Read `SECURITY.md` before network deployment.
- Native-browser layout, animation rendering, Windows execution, Docker build, paid providers and actual local embedding-model inference were not verified in this environment. UI logic and backend behavior were tested; optional adapter failures were tested.

## Project documentation

- `START_HERE.md`: quick demonstration startup.
- `docs/demo-script.md`: five-minute viva walkthrough.
- `docs/architecture.md`: implemented architecture and data model.
- `docs/api-and-events.md`: role boundaries, endpoints and event contract.
- `docs/viva.md`: 30 viva questions and answers.
- `docs/phases.md`: completion checkpoints and scope decisions.
- `docs/verification.md`: test evidence, benchmark context and measured resume bullets.

GitHub destination: `harshsaini-dev/orchestra-ai` (private repository created earlier). **No code has been pushed. Publication requires the user's approval.**
