# 30 viva questions and answers

1. **What problem does the project address?** Business records, policy documents and approval actions often sit in separate tools. OrchestraAI connects them while retaining the evidence and authority for each action.

2. **What is the academic title?** Design and Development of a Multi-Agent AI System for Intelligent Business Workflow Automation.

3. **Why use multiple agents?** Each handler has a bounded responsibility and typed interface: data analysis, enquiry, policy checks, proposals, reporting, notification or verification. Their work and failures can be inspected separately.

4. **Are these autonomous LLM agents?** The default agents are deterministic software roles coordinated by an explicit DAG. Optional LLM output is a draft summary, not an autonomous tool authority.

5. **What does the Orchestrator do?** It selects an allowlisted workflow, dispatches typed requests, persists progress, sequences dependencies and handles the supported read retry.

6. **What makes the bus typed?** Pydantic validates both the message envelope and registered handler payload. Unknown message types and extra envelope fields are rejected.

7. **Why SSE instead of WebSockets?** The browser needs server-to-client progress, while commands already use HTTP. SSE supplies event IDs, reconnect semantics and a simple streaming channel.

8. **How is replay safe?** It reads persisted events and changes display state only. It does not replay tool calls, approve proposals or resubmit jobs.

9. **What are the agent states?** Idle, thinking, retrieving, working, waiting_approval, done, error, recovering and cancelled, with explicit legal transitions.

10. **How is recovery demonstrated?** A controlled first Data read raises an error. The bus transitions through recovering and the second attempt succeeds. Mutation transactions are never automatically retried.

11. **How is multi-tenancy enforced?** The session identifies a user, membership supplies their role, and every item query includes the authorized company. Supplying another company's item ID is insufficient.

12. **What do Owner, Manager and Analyst mean?** Analysts read and analyze. Managers additionally upload, edit and approve operational work. Owners also publish policy, administer memberships and enable the narrow autopilot.

13. **Why SQLAlchemy and SQLite?** SQLAlchemy gives explicit sessions and parameterized queries; SQLite makes the project portable with no separate database service. Its single-process workload limits are documented.

14. **How are uploaded records stored?** As tenant-owned dataset items containing structured JSON rows and a profile. This supports varying CSV schemas but is less scalable than normalized analytical tables.

15. **What files are supported?** CSV, XLSX, text-extractable PDF, DOCX, TXT and Markdown. The system enforces upload, row, PDF-page, text and expanded-archive bounds.

16. **How are chunks created?** Heading-aware blocks are split into 220-word windows at a 180-word stride. PDF page numbers are preserved; other formats use sections without invented page numbers.

17. **What is the default hybrid retrieval?** BM25 and TF-IDF cosine produce separate ranks. Reciprocal rank fusion and lexical overlap reranking combine them. This fallback is lexical, not dense semantic retrieval.

18. **Why reciprocal rank fusion?** Different retrieval scores have different scales. RRF combines their order using a denominator of 60 plus rank, avoiding direct addition of incompatible raw scores.

19. **What does optional Chroma add?** Tenant-separated vector collections using locally installed sentence embeddings. Active SQLite chunks and versioned IDs remain authoritative. Inference was not verified in this delivery environment.

20. **When does the system abstain?** When no active, unflagged passage has enough lexical overlap. Abstention is preferable to inventing a policy answer, but the heuristic can still have false positives and negatives.

21. **Can prompt injection authorize an action?** No. Retrieved text is evidence only. Tool names, rule tables, role checks and mutation paths are controlled by code. Phrase flags add visibility but are not the sole security boundary.

22. **How does policy text become executable?** A conservative parser proposes supported values, then an Owner reviews the values, exceptions and rationale before publishing a structured rule version. Unsupported prose is not compiled.

23. **How does the simulator work?** It evaluates the same records under current and proposed rule tables, records outcome changes and sums affected record value. It does not claim financial savings.

24. **What prevents stale approvals?** The approval transaction checks issue version, dataset version, governing policy identity/version and source document version. Changed evidence requires a new review.

25. **How is duplicate execution prevented?** The prior review result is retained by issue version; repeated review returns that result. Refund state is checked and writes occur under the one-process transaction lock.

26. **What does the Auditor verify?** For Q&A, exact source passages; for sales reports, recomputed aggregates; for fixes, actual postconditions inside the transaction. These checks do not prove semantic truth or business correctness beyond their defined scope.

27. **Why does a PO draft leave health unchanged?** A draft does not physically replenish stock. Only a change to the underlying condition closes it. The score is an explained weighted issue-count heuristic.

28. **Is the audit chain tamper-proof?** No. It detects inconsistency against its current linked history. Someone controlling the entire database can rewrite every hash; an external trusted anchor would be needed for stronger guarantees.

29. **How was the system evaluated?** Backend/security regression tests, real HTTP/SSE UI flows in a DOM emulator, five golden retrieval questions, ten default-rule boundaries, exact-passage validity, measured latency and one injected read-recovery trial. See the saved measurements rather than generalized accuracy claims.

30. **What would you change for production?** Externalize the queue, normalize and migrate data, add stronger identity lifecycle and distributed limits, harden uploads, anchor audit history externally, introduce monitored ERP integrations, and validate deployment, browser behavior and live models in the target environment.
