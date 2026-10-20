# Phase 2 verification — 20 October 2026

Story: submit an order request → FastAPI validates it → the queue dispatches typed agent messages → SQLite records decisions and trace events → SSE updates the workspace → a human review commits one permitted synthetic mutation → replay reads the recorded events.

## Results

| Boundary | Result | Evidence |
|---|---|---|
| Python regression and new bus checks | Passed | 88 passed, 1 skipped, 1 warning; pytest coverage run completed in 26.55 seconds |
| Measured statement coverage | Passed | 538/558 statements covered (96% rounded) across app.core, app.agents, app.service and app.jobs |
| Message validation/dispatch | Passed | Invalid payloads and unknown recipients cannot execute handlers; envelopes are recorded before dispatch |
| Concurrency | Passed | Six concurrent status requests retain independent trace IDs and states |
| Approval transaction | Passed | Existing stale-policy, stale-order, duplicate-refund and rollback tests remain passing |
| Persistence/replay | Passed | Restart preserves trace records; repeated reads leave a single refund and order version 2 |
| Frontend initialization | Passed in DOM emulator | Actual index.html and JS initialize six graph nodes and load eight orders from the API |
| SSE → graph/feed/timeline | Passed in DOM emulator | 48 stream events consumed in the recorded integration run; approval state, packets' message records, four timing rows and feed text checked |
| Keyboard and review UI | Passed in DOM emulator | Enter selects Policy node; review form executes one approved cancellation |
| Replay/theme | Passed in DOM emulator | Historical replay disables review actions and does not repeat mutation; theme changes to light |
| JavaScript syntax | Passed | node --check for static/app.js and static/graph.js |
| CLI demonstration | Passed | Temporary database request → approval → cancelled/refunded order, version 2 |
| Real browser visual layout and animation | Not verified | The connected browser could not reach the sandbox development server; the cloud browser's loopback endpoint was a different service |
| Optional Chroma/Gemini RAG | Not rerun | Optional dependency-based module skipped; no live provider request made |

The DOM emulator does not render pixels, validate responsive geometry or execute SVG motion-path geometry. Animation, hover/perspective quality, contrast and mobile layout need a real-browser inspection on the running project. No screenshot is presented as if that inspection occurred.

The first DOM test relied on the emulator's initial select state and ran a status query; the test now explicitly clicks the Cancellation scenario, following the documented demo. The resulting cancellation/approval flow passes. Backend compatibility fixes also preserved 404 for missing workflow reviews and updated export assertions for the new trace field.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=app.core --cov=app.agents --cov=app.service --cov=app.jobs --cov-report=term-missing
npm ci
$env:ORCHESTRA_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm run test:ui
```

The Node test starts a disposable loopback server on port 8767 and a temporary database. Override `ORCHESTRA_TEST_PORT` if that port is occupied. It does not use or alter the dashboard's database. Node is not required to run the application.

Raw Python evidence: `phase2-tests.xml` and `phase2-coverage.json`. Coverage excludes the optional RAG engine and all unimplemented future modules. Starlette emits a deprecation warning for its httpx TestClient path; it did not prevent these checks from passing.

## Remaining project work

This is the requested Phase 2 runnable checkpoint. It adds event/message contracts, separate agent modules, explicit states, persistent traces and the live isometric interface. It does not implement company workspaces, bulk business-data ingestion, local hybrid document RAG, versioned Policy Studio, the what-if simulator, issue fixing, reports, scheduling, authentication, hash-chain integrity, evaluation UI, or chaos retries. Those remain the subsequent phases in the approved architecture.
