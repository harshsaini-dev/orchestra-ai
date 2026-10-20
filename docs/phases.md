# Delivery phases and completion record

The user approved continuing through all remaining phases and requested a single final project. The previously delivered Phase 2 checkpoint remains separate. This release extends that code instead of replacing the original safeguards.

| Phase | Delivered checkpoint | Verification evidence |
|---|---|---|
| 1 | Existing archive review and architecture proposal | Original 75-test baseline; `architecture-proposal.md` |
| 2 | Modular original agents, typed bus, traces and first isometric UI | Earlier 88-test checkpoint; `phase2-verification.md` |
| 3 | Company accounts/memberships, SQLAlchemy workspace catalog, six loaders/profiles, 1,180-row synthetic business | Tenant, role, loader, profile and seed tests |
| 4 | Offline fused retrieval, cited answers, source inspector/reindex, optional dense/provider boundaries | Retrieval, abstention, injection flags and fallback tests |
| 5 | Five rule categories, policy versions, clause drafts, conflicts, source revisions and impact simulation | Boundary, version, source-change and simulator checks |
| 6 | Issue detection, review/reject, informed edits, idempotent verified actions and narrow autopilot | Stale-input rejection, duplicate prevention and postcondition tests |
| 7 | Audited reports/PDFs, internal notifications, persisted schedules, role controls and audit chain | PDF parsing, scheduler, access and tampering tests |
| 8 | Ten-screen final UI, CSS 3D/isometric animation, actual SSE/replay, benchmarks and controlled recovery | Twelve DOM/API UI checks, golden evaluation and recovery tests |
| 9 | Final regression evidence, source fixtures, Docker/Compose configuration, CI and viva/run documentation | `verification.md`, XML/JSON results and final ZIP |

## Deliberate implementation choices

- The new SQLAlchemy database is additive and preserves the earlier order database. There is no destructive migration or automatic cross-company import.
- Workspace modules follow the implemented responsibilities under `app/workspace/`; the more deeply nested Phase 1 proposal was simplified to keep the project navigable.
- All required operational demonstrations work in deterministic offline mode. Optional dense/model adapters are included but actual live inference was not verified.
- The policy parser is conservative and drafts supported phrases. It does not pretend to compile arbitrary legal or business prose.
- Approval is a separate authenticated transaction after a proposal DAG completes. The issue is the review checkpoint; the original engine retains its earlier explicit waiting-approval trace.
- Notifications are internal. Refunds are simulated, and purchase orders remain drafts. No real external business system is connected.
- The frontend uses plain JavaScript, CSS 3D and SVG isometric geometry rather than a heavy WebGL runtime. It includes motion reduction and keyboard access.
- Browser dictation is optional and asks before using a browser speech service. A Hindi translation layer is not included.
- The Docker and CI definitions are delivered as configuration. Neither a Docker build nor a GitHub CI run occurred here; no code was pushed.
