# Final verification — 20 October 2026

## Executed environment

Linux, Python 3.12.14 and Node 24.19.0. Dependencies installed into an isolated virtual environment. All application tests used temporary databases; no real company account or production service was exercised.

## Results

| Check | Observed result |
|---|---|
| Python regression suite | **101 passed, 1 skipped**, one Starlette/TestClient deprecation warning |
| Overall application line coverage | **85.27%** (2125/2492 statements) |
| Shared agents/core and workspace, excluding optional dense/provider adapters | **94.58%** (1395/1475 statements) |
| Final UI DOM/API integration | **12 checks passed**, 112 actual SSE events consumed |
| JavaScript syntax | `console.js` and `spatial.js` checked with Node |
| New Python module static checks | Ruff undefined/unused checks passed; source formatted |
| Handbook export | Parsed successfully as a 12-page PDF |
| Report export | Generated PDF returned by authenticated report endpoint |
| Docker build | Not run: Docker unavailable |
| Native browser visual/layout/GPU checks | Not run: available browser surfaces could not reach the local development server |
| Windows runtime | Commands documented; not executed on Windows |
| Live LLM/local embedding inference | Not run; fallback/fusion paths tested |

`final-tests.xml` is the pytest result, `final-coverage.json` contains coverage counters, and `final-ui-verification.json` lists the UI checks. The skipped suite belongs to optional legacy Chroma integration. It must not be counted as a pass. The warning is the framework's deprecated httpx TestClient bridge, not a failed assertion.

The UI test registers an account through the form, creates and seeds a company, consumes real SSE, inspects a graph node by keyboard, generates a PDF report, approves a simulated refund with evidence, opens a source citation, compares policies, runs evaluation, replays saved events, changes theme, opens the command palette and visits all ten pages. It uses Happy DOM; it does not validate pixels or CSS rendering.

## Measured golden benchmark

| Metric | Measured value and denominator |
|---|---|
| Retrieval hit@5 | 5/5 known demo-section questions |
| Exact-source citation validity | 8/8 returned citations |
| Default-policy boundary accuracy | 10/10 fixed cases |
| Median retrieval + extractive answer latency | 0.728 ms in this local fixture |
| Maximum question latency | 1.077 ms in this local fixture |
| Read recovery | 1/1 injected trial; 2 attempts |
| Unsupported query | Abstained |

These are small-fixture measurements, not general performance promises. Citation validity verifies exact text/source identity, not semantic entailment. The benchmark calls retrieval directly; timings exclude HTTP, rendering, optional model inference and realistic concurrent production load. Repeat with `python -m scripts.evaluate`; latency will vary.

## Defects caught and resolved

- Terminal SSE ordering was changed so a stream cannot close before its final event is persisted.
- Source edits/reindexing invalidate referenced policy evidence before operational execution.
- Dataset and policy changes reject older approval proposals; repeat review returns the prior result.
- Golden policy traces use the currently published numeric values rather than hardcoded original clause amounts.
- Optional dense/provider failures retain the offline answer with a visible warning.
- The old unauthenticated endpoints are disabled by default; legacy regression tests explicitly opt in.

## Honest resume bullets

- Built a FastAPI/SQLAlchemy multi-company academic workflow system with eight agent roles, six explicit DAGs and ten vanilla-JavaScript workspace screens.
- Implemented source-cited BM25/TF-IDF retrieval and versioned rule approvals, verified with 101 passing Python tests and 85.3% overall line coverage in the delivery environment.
- Added persisted SSE/replay, transaction-checked simulated actions, hash-linked audit evidence and a reproducible 1,180-record synthetic SME dataset.
- Evaluated five known retrieval questions and ten policy-boundary cases with complete fixture hits; reported measured latency and scope instead of claiming general accuracy or business savings.

## Publication status

The private `harshsaini-dev/orchestra-ai` repository exists from the earlier approved creation step. Project source is prepared locally. **Nothing has been pushed or deployed.** User approval is required before GitHub publication.
