# Security model

The default installation binds to loopback and is intended for local academic use. It provides authenticated workspace isolation and controlled simulated operations. It is not a production financial system.

## Implemented boundaries

- Passwords are salted PBKDF2 hashes; random session tokens are stored hashed, expire after 12 hours and use HttpOnly/SameSite=Strict cookies.
- Every workspace endpoint derives the user from the session and the role from server-side membership. Object queries include the selected company. Owner, Manager and Analyst permissions have integration tests.
- Mutation requests with an Origin header must match the request host. TrustedHostMiddleware rejects unconfigured hosts. API responses are no-store; MIME sniffing and framing are disabled.
- Structured rule and action code is allowlisted. Questions do not become raw SQL. Uploaded text and LLM drafts never grant execution authority.
- Approval checks occur in one locked database transaction and include issue/dataset/policy/source versions. Repeat review cannot execute the same approved record twice. Postcondition failure rolls back the transaction.
- Uploads have byte, row, PDF-page, extracted-text and Office-expansion limits. Office macros are not executed. Scanned PDF OCR is not provided. Original uploaded binaries are not retained; extracted data/text is stored.
- Audit entries link canonical actor/action/detail JSON to the previous hash. The API verifies the full tenant chain. A database administrator can rewrite the entire chain; no external anchor is claimed.
- Secrets, local databases, model binaries, caches and dependency directories are excluded from the delivery archive and Git source.

## Deployment decisions

Use exactly one Uvicorn worker. For any network-facing deployment, configure HTTPS and `ORCHESTRA_SECURE_COOKIE=1`, set exact `AGENTFLOW_ALLOWED_HOSTS`, and decide when to set `ORCHESTRA_DISABLE_SIGNUP=1`. Provide a persistent volume and application-consistent backups. Do not enable `ORCHESTRA_LEGACY` on a shared service: it intentionally restores the unauthenticated earlier sandbox for local regression/demo work.

No MFA, password reset, email ownership verification, distributed rate limiting, antivirus pipeline, externally anchored audit chain, disaster-recovery service or production monitoring is included. Sign-in throttling is process-local and resets at restart. Workload bounds do not replace production ingress limits.

Optional model requests can send the user's question and cited company passages to the configured provider. They are disabled by default and require server-side configuration. Browser dictation may use the browser vendor's remote speech service; the UI asks before starting it. Notifications otherwise remain in the local application inbox.

## Data retention and backups

`workspace.db` contains accounts, records, source extracts, reports, events and audit evidence. `agentflow.db` contains the separate legacy sandbox. Stop the app before copying the `data` directory, or use SQLite's backup API. Preserve WAL files if taking a filesystem-level snapshot while a process is active. Avoid committing either database. The old `scripts.reset_demo` resets only the legacy order sandbox and must not be mistaken for a workspace backup or reset tool.

## Verified and unverified

Automated tests cover tenant crossing, roles, cross-origin mutations, stale approvals, idempotency, upload types/limits, document changes, audit tampering and safe fallback. They do not constitute a penetration test. Actual model inference, paid provider calls, native-browser GPU/layout behavior, Windows execution and Docker build remain unverified in this environment.
