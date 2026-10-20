> Historical AgentFlow baseline documentation. Read the current root README and docs/phase2-verification.md for this checkpoint.

# Verification — AgentFlow v0.7

Build date: 13 October 2026. Intended practical: 14 October 2026.

## Automated checks

**87 passed.** Actual output is in `test-results.txt` and `test-results.xml`.

Coverage includes 32 seeded order/intent scenarios, atomic approvals and rollback, duplicate-refund protection, concurrent reviews, policy changes, refund-window boundaries, job idempotency, persisted progress before a blocked agent completes, cancellation, failed jobs, bounded queue capacity, restart interruption, SSE reconnect cursors, and execution-trace export.

Tests use temporary databases. The queue capacity test fills all eight outstanding slots, verifies HTTP 429 for the ninth job, releases the workers, and checks that another job can then run.

## Browser verification

Chromium 134 / Playwright 1.51.0 exercised the real FastAPI server and a temporary SQLite database.

| Flow | Result |
|---|---|
| Live progress | Running agent visible before workflow persistence |
| Refresh mid-run | Restored active job, reconnected events, reached approval checkpoint |
| Inspector | Displayed actual policy retrieval output |
| Approval | Action state streamed; order became cancelled/refunded, version 2 |
| Replay | Reconstructed past states without another database mutation |
| Stop | Cancelled planning at an agent boundary, leaving order unchanged |
| Normal speed | Completed request/rejection without presentation delay |
| History | Search, status filter, CSV export and reopening trace worked |
| Mobile | No horizontal page overflow at 390px |
| JavaScript | No uncaught browser errors |

See `browser-verification.json`. Screenshots used to inspect the new layout were internal QA images. The `previous-milestone-v0.5` folder preserves the earlier package's historical report/screenshots and is not evidence for the current interface.

The ZIP contains no runtime database. A fresh install starts with eight synthetic orders. `sample-audit.json` is a historical example from the browser test, including the business audit and live execution traces.

## Remaining verification limits

- Live Gemini calls were not tested: no user key was supplied. Success/failure adapter paths use mocks.
- Windows launcher execution was not tested here. Application and browser checks ran on Linux / Python 3.12; run `start.bat` on the target laptop before the practical.
- No real payment gateway, production identity system, or external commerce integration exists.
- The worker queue is single-process and local. It is not a distributed scheduler, does not automatically replay interrupted jobs, and was not load-tested for production.

Default offline mode is deterministic multi-agent orchestration. Optional Gemini assistance does not make every agent an independent model.

## v0.7 RAG verification

Twelve additional tests cover chunk overlap, actual Chroma indexing/retrieval, embedding REST payload and normalization, upload deduplication, PDF page extraction, deleted-source exclusion, invented-citation blocking, insufficient-context handling, missing-key failures, embedding-model isolation and RAG workflow approvals. Provider responses are mocked; ChromaDB 1.5.9 and SQLite are real.

A separate browser story verified upload → chunk inspection → indexing → retrieval-only preview → cited generation → RAG-assisted live workflow → approval → order update, and the RAG layout at 390px. See `rag-browser-verification.json`. The UI displayed the test provider's explicit `TEST-DOUBLE-NOT-A-LIVE-MODEL` label during these checks. No test provider is wired into the shipped application.

This does not verify actual Gemini latency, quota, billing, semantic retrieval quality, grounding quality or resistance to every document prompt injection. Run a real indexing and answer request with your own key before claiming live-model success.
