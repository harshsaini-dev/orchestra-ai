> Historical AgentFlow baseline documentation. Read the current root README and docs/phase2-verification.md for this checkpoint.

# Practical demonstration and viva notes

## Opening explanation (English)

My project is titled “Design and Development of a Multi-Agent AI System for Intelligent Business Workflow Automation.” The current milestone implements a controlled order-exception workflow. Specialised components plan the request, read order data, retrieve policies, evaluate eligibility and execute an approved action. Sensitive operations pause for human approval. Every step is stored in an audit trail.

The current offline demonstration uses deterministic rules. Gemini assistance is implemented as an optional integration, but I will only describe it as live-tested after configuring and successfully testing my own key.

## Opening explanation (Hinglish)

Sir, is project mein ek business request ko alag responsibilities wale agents handle karte hain. Planner request ka intent identify karta hai, Data Agent order ki information read karta hai, Policy Agent relevant rules retrieve karta hai, aur Decision Agent eligibility check karta hai. Cancellation ya refund ke liye system human approval par rukta hai. Approval ke baad Action Agent permitted operation perform karta hai aur complete record database mein save hota hai. Is demo mein payment simulated hai.

## Demo sequence

1. **Live console:** point out the offline mode and sample orders.
2. **Cancellation:** click Cancellation → Start workflow with Presentation pace enabled.
3. **Live map:** identify which agent is working. Explain the separate responsibilities.
4. **Policy inspector:** click Policy → Output & evidence. Show POL-CANCEL and the actual retrieval output.
5. **Human checkpoint:** Action waits. Enter your name and approve. The simulated cancellation/refund commits atomically.
6. **Comparison:** show the request snapshot and current cancelled/refunded order, version 2.
7. **Replay:** click Inspect past steps, move the slider, then Return to full trace. No action is executed again.
8. **Exception:** select ORD-1002, Cancel order, Start workflow. Its shipped state causes escalation.
9. **Rejection:** click Refund, Start workflow, enter your name, Reject action. Payment remains unchanged.
10. **Persistence and exports:** refresh during a paced run to demonstrate reconnect. Filter Run history, reopen a trace, download JSON/CSV.

Sample choices populate the form; they do not secretly execute workflows. Run and approval buttons call real API endpoints. The interface displays stored events, not a fabricated animation.

## Likely questions

**1. Why multiple agents?**
Responsibilities are separated so data access, retrieval, decisions and actions can be understood, tested and controlled independently. The current prototype is coordinated and bounded; it is not a free-form conversation between autonomous models.

**2. What is the orchestrator?**
`WorkflowService` coordinates the components, carries shared state, chooses the next step and persists the result. A sensitive action enters `pending_approval` and resumes when reviewed.

**3. Is every agent an LLM?**
No. The agents are specialised software components. The default mode is deterministic. Gemini can classify intent and produce a policy-grounded explanation, while code enforces eligibility and permissions.

**4. Where is RAG?**
The Policy Agent retrieves relevant documents using BM25 lexical ranking and intent routing. In Gemini mode these excerpts are provided to the model for generation. Offline mode provides retrieval and rule-based responses. The v0.7 Document RAG option additionally uses Gemini semantic embeddings and a persistent ChromaDB collection. It generates an answer with retrieved source IDs and exact supporting quotes. Uploaded PDF/TXT/Markdown files are available in the RAG knowledge workspace.

**5. Why SQLite?**
It runs locally without a separate database server and is sufficient for a low-resource, single-machine prototype. Larger deployments would need stronger operational controls and a production database strategy.

**6. What prevents unauthorised actions?**
Tool allowlists, validated inputs, mandatory stored approval and deterministic policy checks constrain actions. This local milestone does not authenticate reviewer identity; proper user authentication and roles are pending.

**7. What prevents duplicate refunds?**
Only a pending workflow can be approved. SQLite transactions serialise writes, each order refund is unique, and order-version checks invalidate competing pending workflows.

**8. What if the order changes before approval?**
The service compares the current order version and policy fingerprint and recomputes eligibility. If anything relevant differs, it blocks execution and escalates the workflow.

**9. What if an operation fails halfway?**
The approval, order update, refund ledger and audit events are committed together. A failure rolls back the transaction. A test intentionally injects a failure to verify this behaviour.

**10. What happens without the internet?**
After dependencies are installed, the dashboard and default flow work offline. A requested Gemini call that fails is visibly recorded as a fallback. No generated answer is falsely labelled as a successful live model response.

**11. Is the refund real?**
No. The system updates synthetic database records and a simulated refund ledger. No payment gateway is connected.

**12. How much is complete?**
The local order workflow, dashboard, policy retrieval, approvals, persistence and tests are implemented. Production identity, larger-corpus retrieval evaluation, live model validation and external integrations remain. Version 0.7 is a milestone label, not an objective percentage.

**13. What is the difference between an API and an agent?**
An API exposes an operation to other software. An agent component is responsible for part of the workflow and uses data or permitted tools to fulfil it. FastAPI is the entry point; the service and agents implement the workflow behind it.

**14. How are monetary values stored?**
As integer paise, avoiding binary floating-point errors in stored currency amounts. Formatting to rupees is only for display.

## Before leaving for the practical

- Install dependencies tonight and start the project successfully on your own laptop.
- Rehearse approval, rejection and escalation.
- Keep the ZIP and these practical notes available offline.
- Keep the server bound to 127.0.0.1; do not publish this local demo.
- Explain completed and pending work accurately.

## New live-progress viva questions

**How does the screen update without refreshing?**
The browser opens an EventSource connection. FastAPI streams persisted job events using Server-Sent Events. Events contain IDs, agent names, actual start/end states, timestamps and details.

**Are the five agents working in parallel?**
Within one request, these stages follow dependencies and run sequentially. The worker queue can process two separate jobs concurrently. The map shows the actual stage; it does not claim parallel execution.

**Why is there a pause?**
Presentation pace is an explicitly labelled teaching option. It adds 0.8 seconds before a stage begins its work. Turning it off removes the delay. Compute duration is measured separately.

**What happens on refresh or restart?**
A browser refresh reconnects to the saved job and deduplicates events by ID. A server restart marks unfinished jobs interrupted instead of blindly repeating business actions. Stored approvals and orders remain in SQLite.

**What does replay do?**
It reconstructs agent states from saved events. It does not call the agents or change records. Review buttons are disabled while inspecting historical steps.

## RAG demo and explanation

1. Configure the key and build the vector index before the practical.
2. Open RAG knowledge. Show the document/chunk counts and inspect one chunk.
3. Ask: "When is a delivered order eligible for a refund?" using Retrieve only. Explain that this is context, not a generated answer.
4. Click Retrieve & generate. Show the LLM answer, source references, exact quotes, page/chunk metadata and measured timings.
5. Upload `data/sample_support_handbook.txt`, rebuild, and ask: "What information should a customer provide to support?"
6. Enable Document RAG in the live console and run an order workflow. Show Chroma context in the Policy Agent inspector and the generated explanation in the Decision Agent output.

**Hinglish:** Document pehle chunks mein divide hota hai. Embedding model chunks ko numeric vectors mein convert karta hai, jo ChromaDB mein store hote hain. Question ka bhi embedding banta hai. Similarity search relevant passages retrieve karti hai. Gemini ko question aur ye passages diye jaate hain; answer ke saath source references dikhte hain. Model ko refund approve karne ka right nahi milta.

**Why not a local embedding model?** This laptop-oriented prototype uses provider embeddings to avoid downloading/running an additional language model locally. Chroma stores/searches vectors locally. RAG needs internet and API access.

**Are citations a guarantee of correctness?** No. The server checks source IDs and exact supporting quotes. A reviewer must still assess whether the answer's claims are supported. If a citation is invented, the answer is blocked.

**What if the answer is absent?** The model is instructed to abstain. An insufficient-context response is explicitly labelled, with no fabricated answer substituted. Abstention quality with real models still needs evaluation.
