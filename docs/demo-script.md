# Five-minute demonstration

Prepare a fresh company workspace and load demo data before presenting. Leave optional providers disabled. Explain that all business records are synthetic and financial effects are simulated.

| Time | Screen and action | Explain |
|---|---|---|
| 0:00–0:35 | Command center; show dataset/record counts and the network | “The system connects company data and policies through typed agent messages. The graph displays persisted server events.” |
| 0:35–1:15 | Run Weekly sales report; optionally inject one read failure | Follow Data → Report → Auditor → Notification. Click Data to inspect its evidence. Show real error/recovering events and measured handler duration. |
| 1:15–2:00 | Ask your business: “What are the refund approval requirements?” | Open a citation. Show the exact handbook passage and version. In Knowledge, inspect BM25, TF-IDF and fused ranks. Ask an unsupported question to demonstrate abstention. |
| 2:00–2:50 | Scan workspace, then Issues & fixes → Refund | Read the record, threshold, policy/source versions and proposed simulation. Approve once; explain transaction-local verification and repeat-request protection. |
| 2:50–3:30 | Open a low-stock issue and approve a PO draft | Show the operational draft. Emphasize that stock has not increased and the condition remains open. |
| 3:30–4:15 | Policy studio; change refund threshold from 5000 to 10000, Compare impact | Show decision flips and affected record value. This is not savings. Do not publish unless you intend to revise the workspace policy. |
| 4:15–4:40 | Evaluation; run benchmark | State the actual denominators: five golden questions, ten rule-boundary cases, exact-source citation validation and one recovery trial. |
| 4:40–5:00 | Audit & settings, then Runs & replay | Show chain verification and a saved run. Explain that replay reads events and executes no tools. |

If a proposal returns a stale-version conflict after editing a dataset or policy, rerun the scan and inspect the new proposal. This is an intended governance safeguard, not a failed workflow.

Optional extension: edit a document, try to approve a related proposal, show the source-version block, then review the clause draft and publish a revised policy as Owner.

## Troubleshooting during presentation

- No records: use a fresh workspace and Load demo data. Seeding refuses to overwrite a workspace that already has datasets.
- No citations: ask about content that exists in the selected company's active documents; inspect the source shelf.
- A run errors: open its saved result. Do not claim it succeeded. Check the server terminal for the full exception.
- The UI reports a stale proposal: run another scan before approving.
- Login cookie missing: use the same hostname throughout; do not alternate `localhost` and `127.0.0.1`.
- Docker/Windows/model demos should be rehearsed in the target environment. They were not executed during this delivery's Linux verification.
